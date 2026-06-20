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
 *   TACET_HOTKEY_FD — parent writes 'H' on hotkey → python3 fires on_activate
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
        log_msg("paste: AX not trusted — attempting CGEventPost anyway");
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
    char self[PATH_MAX]; uint32_t sz = sizeof(self);
    if (_NSGetExecutablePath(self, &sz)) { log_msg("ERROR: _NSGetExecutablePath"); return 1; }
    char real_self[PATH_MAX];
    if (!realpath(self, real_self)) { log_msg("ERROR: realpath"); return 1; }
    char *sl = strrchr(real_self, '/'); if (!sl) { log_msg("ERROR: bad path"); return 1; }
    *sl = '\0';
    sl = strrchr(real_self, '/'); if (!sl) { log_msg("ERROR: bad path"); return 1; }
    *sl = '\0';

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
