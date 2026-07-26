#import <Cocoa/Cocoa.h>
#import <Carbon/Carbon.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <pthread.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <mach-o/dyld.h>

/*
 * Tacet native launcher — Contents/MacOS/tacet
 *
 * Two IPC channels with python3:
 *   TACET_PASTE_FD  — python3 writes 'P' → parent calls CGEventPost(Cmd+V)
 *   TACET_HOTKEY_FD — parent → python3 event bytes:
 *     'H' hotkey pressed          → python fires on_activate
 *     'A' Accessibility granted   → paste is live (sent at startup if already
 *                                   trusted, or by the AX poll thread on flip)
 *     'N' paste refused           → CGEventPost skipped because AX not trusted;
 *                                   text stays on the clipboard for manual Cmd+V
 *   Single-byte pipe writes are atomic, so the hotkey handler (main thread),
 *   AX poll thread, and paste thread can all share the write fd safely.
 *
 * Hotkey: Carbon RegisterEventHotKey (ctrl+shift+space).
 *   Requires NO TCC permission (neither Accessibility nor Input Monitoring).
 *   Requires NSApplication to be running so GetApplicationEventTarget() exists.
 *
 * Thread layout (parent after fork):
 *   Main thread  — [NSApp run], receives Carbon hotkey events, writes 'H'
 *   Paste thread — blocking read() on paste pipe; calls do_paste() on 'P'
 *
 * Fork happens BEFORE [NSApplication sharedApplication] so the child does not
 * inherit the parent's Window Server connection.
 */

/* ── Child PID for signal forwarding ──────────────────────────────────────── */

static volatile pid_t g_child_pid = 0;

static void sig_forward(int sig) {
    if (g_child_pid > 0) kill(g_child_pid, sig);
}

/* ── File logging ──────────────────────────────────────────────────────────── */

static int g_log_fd = -1;

static void open_log_file(void) {
    const char *home = getenv("HOME");
    if (!home) return;
    char dir1[PATH_MAX], dir2[PATH_MAX], path[PATH_MAX];
    snprintf(dir1, sizeof(dir1), "%s/Library/Logs",       home);
    snprintf(dir2, sizeof(dir2), "%s/Library/Logs/Tacet", home);
    snprintf(path, sizeof(path), "%s/launcher.log",        dir2);
    mkdir(dir1, 0755);
    mkdir(dir2, 0755);
    g_log_fd = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
}

static void log_msg(const char *msg) {
    if (g_log_fd < 0) return;
    time_t now = time(NULL);
    struct tm *t = localtime(&now);
    char ts[32];
    strftime(ts, sizeof(ts), "%H:%M:%S", t);
    char line[1024];
    int n = snprintf(line, sizeof(line), "[%s] [tacet] %s\n", ts, msg);
    if (n > 0) write(g_log_fd, line, (size_t)n);
}

/* ── Hotkey: Carbon RegisterEventHotKey (no TCC required) ──────────────────── */

#define HK_KEYCODE   49u                      /* kVK_Space */
#define HK_MODIFIERS (controlKey | shiftKey)  /* 0x1200 */

static int g_hotkey_write_fd = -1;

static OSStatus carbon_hotkey_handler(EventHandlerCallRef callRef,
                                       EventRef event, void *userData) {
    (void)callRef; (void)userData;
    if (GetEventKind(event) == kEventHotKeyPressed) {
        log_msg("hotkey: ctrl+shift+space fired — writing H");
        if (g_hotkey_write_fd >= 0)
            write(g_hotkey_write_fd, "H", 1);
    }
    return noErr;
}

static void setup_carbon_hotkey(void) {
    log_msg("registering Carbon hotkey ctrl+shift+space");
    EventTypeSpec spec = { kEventClassKeyboard, kEventHotKeyPressed };
    InstallApplicationEventHandler(
        NewEventHandlerUPP(carbon_hotkey_handler), 1, &spec, NULL, NULL);
    EventHotKeyID hkID = { 'tact', 1 };
    EventHotKeyRef hkRef = NULL;
    OSStatus st = RegisterEventHotKey(HK_KEYCODE, HK_MODIFIERS, hkID,
                                       GetApplicationEventTarget(), 0, &hkRef);
    if (st == noErr)
        log_msg("Carbon hotkey registered — listening for ctrl+shift+space");
    else {
        char tmp[80];
        snprintf(tmp, sizeof(tmp), "RegisterEventHotKey failed OSStatus=%d", (int)st);
        log_msg(tmp);
    }
}

/* ── Paste via CGEventPost ─────────────────────────────────────────────────── */

static void do_paste(void) {
    if (!AXIsProcessTrusted()) {
        /* Posting would be silently dropped by macOS — tell python instead so
         * the UI can point the user at System Settings. */
        log_msg("paste: AX not trusted — sending 'N' to python, skipping CGEventPost");
        if (g_hotkey_write_fd >= 0) write(g_hotkey_write_fd, "N", 1);
        return;
    }
    CGEventSourceRef src = CGEventSourceCreate(kCGEventSourceStateCombinedSessionState);
    if (!src) { log_msg("paste: CGEventSourceCreate NULL"); return; }
    const CGKeyCode V = 9;
    CGEventRef dn = CGEventCreateKeyboardEvent(src, V, true);
    CGEventSetFlags(dn, kCGEventFlagMaskCommand);
    CGEventPost(kCGHIDEventTap, dn); CFRelease(dn);
    CGEventRef up = CGEventCreateKeyboardEvent(src, V, false);
    CGEventSetFlags(up, kCGEventFlagMaskCommand);
    CGEventPost(kCGHIDEventTap, up); CFRelease(up);
    CFRelease(src);
    log_msg("paste: CGEventPost complete");
}

/* ── Paste pump thread ─────────────────────────────────────────────────────── */

static void *paste_pump_thread(void *arg) {
    int fd = *(int *)arg;
    log_msg("paste thread: started");
    char buf[1];
    while (read(fd, buf, 1) > 0) {
        if (buf[0] == 'P') { log_msg("paste: 'P' received"); do_paste(); }
    }
    close(fd);
    log_msg("paste thread: pipe closed — stopping NSApp");
    dispatch_async(dispatch_get_main_queue(), ^{
        [NSApp stop:nil];
        NSEvent *e = [NSEvent otherEventWithType:NSEventTypeApplicationDefined
                                        location:NSZeroPoint
                                   modifierFlags:0
                                       timestamp:0
                                    windowNumber:0
                                         context:nil
                                         subtype:0
                                           data1:0
                                           data2:0];
        [NSApp postEvent:e atStart:YES];
    });
    return NULL;
}

/* ── AX grant poll thread ──────────────────────────────────────────────────── */

/* Watches for the Accessibility grant arriving while we run (tccd applies it
 * to a live process — no relaunch needed) and tells python with 'A' so the UI
 * can confirm paste is ready. Exits after the first flip. */
static void *ax_poll_thread(void *arg) {
    (void)arg;
    unsigned interval = 1, elapsed = 0;
    log_msg("ax-poll: waiting for Accessibility grant");
    for (;;) {
        if (AXIsProcessTrusted()) {
            log_msg("ax-poll: Accessibility granted — sending 'A' to python");
            if (g_hotkey_write_fd >= 0) write(g_hotkey_write_fd, "A", 1);
            return NULL;
        }
        if (elapsed >= 120) interval = 5;
        sleep(interval);
        elapsed += interval;
    }
}

/* ── Fatal startup failure UI ──────────────────────────────────────────────
 * Early path-resolution failures used to just log_msg() and exit(1), which
 * is invisible to a first-time user who has no reason to go looking in
 * ~/Library/Logs/Tacet. Show something instead of dying silently. */
static int fail_with_alert(const char *reason, NSString *info) {
    log_msg(reason);
    [NSApplication sharedApplication];
    [NSApp activateIgnoringOtherApps:YES];
    NSAlert *alert = [[NSAlert alloc] init];
    [alert setMessageText:@"Tacet Failed to Start"];
    [alert setInformativeText:info];
    [alert addButtonWithTitle:@"Quit"];
    [alert runModal];
    return 1;
}

/* ── Entry point ───────────────────────────────────────────────────────────── */

int main(void) {
    @autoreleasepool {

    open_log_file();
    signal(SIGTERM, sig_forward);
    signal(SIGINT,  sig_forward);

    char tmp[PATH_MAX + 64];
    snprintf(tmp, sizeof(tmp), "launcher starting, pid=%d", (int)getpid());
    log_msg(tmp);

    /* Resolve own path → Contents dir */
    NSString *pathFailInfo = @"Tacet couldn't resolve its own install path. "
        @"Try reinstalling from a fresh download.";
    char self[PATH_MAX]; uint32_t sz = sizeof(self);
    if (_NSGetExecutablePath(self, &sz))
        return fail_with_alert("ERROR: _NSGetExecutablePath", pathFailInfo);
    char real_self[PATH_MAX];
    if (!realpath(self, real_self))
        return fail_with_alert("ERROR: realpath", pathFailInfo);
    char *sl = strrchr(real_self, '/'); if (!sl) return fail_with_alert("ERROR: bad path", pathFailInfo);
    *sl = '\0';
    sl = strrchr(real_self, '/'); if (!sl) return fail_with_alert("ERROR: bad path", pathFailInfo);
    *sl = '\0';

    /* Refuse to run from anywhere but /Applications. A quarantined copy
     * launched straight off a mounted DMG (instead of dragged in first) gets
     * App Translocation'd by Gatekeeper to a randomized read-only path —
     * which breaks the path resolution above/below in ways that fail
     * silently (no log, no python child, no visible error). Catch it here
     * with a real dialog instead of dying invisibly. */
    char bundle_dir[PATH_MAX];
    snprintf(bundle_dir, sizeof(bundle_dir), "%s", real_self);
    char *contents_sep = strrchr(bundle_dir, '/');
    if (contents_sep) *contents_sep = '\0';   /* .../Tacet.app/Contents -> .../Tacet.app */

    int translocated     = strstr(real_self, "/AppTranslocation/") != NULL;
    int not_in_applications = strncmp(bundle_dir, "/Applications/", 14) != 0;

    if (translocated || not_in_applications) {
        snprintf(tmp, sizeof(tmp), "refusing to run from %s (translocated=%d) — showing move dialog",
                 bundle_dir, translocated);
        log_msg(tmp);

        [NSApplication sharedApplication];
        [NSApp activateIgnoringOtherApps:YES];
        NSAlert *alert = [[NSAlert alloc] init];
        [alert setMessageText:@"Move Tacet to the Applications Folder"];
        [alert setInformativeText:@"Tacet needs to run from /Applications to work correctly. "
            @"Quit this copy, drag Tacet.app into your Applications folder in Finder, "
            @"then open it from there."];
        [alert addButtonWithTitle:@"Quit"];
        [alert runModal];
        return 0;
    }

    char resources[PATH_MAX], python[PATH_MAX];
    snprintf(resources, sizeof(resources), "%s/Resources",         real_self);
    snprintf(python,    sizeof(python),    "%s/.venv/bin/python3", resources);
    snprintf(tmp, sizeof(tmp), "resources: %s", resources); log_msg(tmp);
    snprintf(tmp, sizeof(tmp), "python: %s",    python);    log_msg(tmp);

    /* Request Accessibility (needed later for CGEventPost/paste) */
    if (!AXIsProcessTrusted()) {
        log_msg("AX not trusted — requesting Accessibility dialog (needed for paste)");
        CFStringRef key = kAXTrustedCheckOptionPrompt;
        CFDictionaryRef opts = CFDictionaryCreate(NULL,
            (const void **)&key, (const void **)&kCFBooleanTrue,
            1, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
        AXIsProcessTrustedWithOptions(opts);
        CFRelease(opts);
    } else {
        log_msg("AX already trusted — paste ready immediately");
    }

    /* Paste pipe */
    int paste_pipe[2];
    if (pipe(paste_pipe)) { log_msg("ERROR: paste pipe"); return 1; }
    char fd_str[16];
    snprintf(fd_str, sizeof(fd_str), "%d", paste_pipe[1]);
    setenv("TACET_PASTE_FD", fd_str, 1);
    snprintf(tmp, sizeof(tmp), "paste pipe write_fd=%d → TACET_PASTE_FD", paste_pipe[1]);
    log_msg(tmp);

    /* Hotkey pipe */
    int hotkey_pipe[2];
    if (pipe(hotkey_pipe)) { log_msg("ERROR: hotkey pipe"); return 1; }
    fcntl(hotkey_pipe[1], F_SETFD, FD_CLOEXEC);
    g_hotkey_write_fd = hotkey_pipe[1];
    char hk_str[16];
    snprintf(hk_str, sizeof(hk_str), "%d", hotkey_pipe[0]);
    setenv("TACET_HOTKEY_FD", hk_str, 1);
    snprintf(tmp, sizeof(tmp), "hotkey pipe read_fd=%d → TACET_HOTKEY_FD", hotkey_pipe[0]);
    log_msg(tmp);

    if (chdir(resources)) { log_msg("ERROR: chdir"); return 1; }

    /* Fork BEFORE NSApplication init so child doesn't inherit WS connection */
    pid_t pid = fork();
    if (pid < 0) { log_msg("ERROR: fork"); return 1; }

    if (pid == 0) {
        close(paste_pipe[0]);
        snprintf(tmp, sizeof(tmp), "child: execv %s", python); log_msg(tmp);
        char *args[] = { python, "-m", "src.main", NULL };
        execv(python, args);
        log_msg("ERROR: execv failed"); _exit(1);
    }

    /* Parent */
    g_child_pid = pid;
    snprintf(tmp, sizeof(tmp), "forked child pid=%d", (int)pid); log_msg(tmp);
    close(paste_pipe[1]);
    close(hotkey_pipe[0]);

    static int paste_read_fd;
    paste_read_fd = paste_pipe[0];
    pthread_t paste_tid;
    if (pthread_create(&paste_tid, NULL, paste_pump_thread, &paste_read_fd) == 0)
        pthread_detach(paste_tid);
    log_msg("paste thread started");

    /* Tell python whether paste is live. If not yet trusted, poll for the
     * grant so the user can allow it mid-run without relaunching. */
    if (AXIsProcessTrusted()) {
        log_msg("AX trusted at startup — sending 'A' to python");
        write(g_hotkey_write_fd, "A", 1);
    } else {
        pthread_t ax_tid;
        if (pthread_create(&ax_tid, NULL, ax_poll_thread, NULL) == 0)
            pthread_detach(ax_tid);
    }

    /* Init NSApplication (parent only, after fork).
     * Required for GetApplicationEventTarget() to return a valid target. */
    [NSApplication sharedApplication];
    [NSApp setActivationPolicy:NSApplicationActivationPolicyProhibited];
    log_msg("NSApplication initialized (LSUIElement — no dock icon)");

    /* Register Carbon hotkey — no TCC permission required */
    setup_carbon_hotkey();

    /* Run loop — blocks until paste pump calls [NSApp stop:] */
    log_msg("main thread: [NSApp run] entering");
    [NSApp run];
    log_msg("main thread: [NSApp run] returned");

    close(hotkey_pipe[1]);

    int status;
    waitpid(pid, &status, 0);
    snprintf(tmp, sizeof(tmp), "child exited status=%d",
             WIFEXITED(status) ? WEXITSTATUS(status) : -1);
    log_msg(tmp);
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;

    } /* @autoreleasepool */
}
