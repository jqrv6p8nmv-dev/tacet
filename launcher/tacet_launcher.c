#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/wait.h>
#include <mach-o/dyld.h>
#include <ApplicationServices/ApplicationServices.h>

/*
 * Tacet native launcher — lives at Contents/MacOS/tacet.
 *
 * Being a compiled binary at the canonical CFBundleExecutable path means
 * macOS TCC attributes permission requests to the "Tacet" bundle (via
 * Info.plist) rather than to python3 / Python.framework.
 *
 * Steps:
 *   1. Resolve Contents/Resources from our own path
 *   2. Trigger the Accessibility permission prompt as "Tacet"
 *   3. Create a paste pipe: python3 writes 'P' to signal "do Cmd+V now"
 *   4. Fork python3 from the bundled venv; pass write-fd via TACET_PASTE_FD
 *   5. Parent stays alive pumping paste requests via CGEventPost (we have
 *      Accessibility — python3's Python.framework identity does not)
 *   6. When the pipe closes (python3 exits), waitpid and exit
 */

/* Simulate Cmd+V via CGEventPost — requires Accessibility on *this* process */
static void do_paste(void) {
    CGEventSourceRef src = CGEventSourceCreate(kCGEventSourceStateCombinedSessionState);
    if (!src) return;

    const CGKeyCode V_KEY = 9;

    CGEventRef down = CGEventCreateKeyboardEvent(src, V_KEY, true);
    CGEventSetFlags(down, kCGEventFlagMaskCommand);
    CGEventPost(kCGHIDEventTap, down);
    CFRelease(down);

    CGEventRef up = CGEventCreateKeyboardEvent(src, V_KEY, false);
    CGEventSetFlags(up, kCGEventFlagMaskCommand);
    CGEventPost(kCGHIDEventTap, up);
    CFRelease(up);

    CFRelease(src);
}

int main(void) {
    /* Resolve our own path (avoids relying on argv[0] which can be spoofed) */
    char self[PATH_MAX];
    uint32_t self_size = sizeof(self);
    if (_NSGetExecutablePath(self, &self_size) != 0) {
        fprintf(stderr, "[tacet] _NSGetExecutablePath failed\n");
        return 1;
    }
    char real_self[PATH_MAX];
    if (realpath(self, real_self) == NULL) {
        perror("[tacet] realpath");
        return 1;
    }

    /* real_self = .../Tacet.app/Contents/MacOS/tacet
     * Strip filename → MacOS dir, strip MacOS → Contents dir */
    char *slash = strrchr(real_self, '/');
    if (!slash) { fprintf(stderr, "[tacet] bad path\n"); return 1; }
    *slash = '\0'; /* → .../Contents/MacOS */
    slash = strrchr(real_self, '/');
    if (!slash) { fprintf(stderr, "[tacet] bad path\n"); return 1; }
    *slash = '\0'; /* → .../Contents */

    char resources[PATH_MAX], python[PATH_MAX];
    snprintf(resources, sizeof(resources), "%s/Resources", real_self);
    snprintf(python,    sizeof(python),    "%s/.venv/bin/python3", resources);

    /* Trigger the Accessibility permission prompt branded as "Tacet".
     * If already granted this returns immediately; if not, macOS shows
     * "Tacet wants to control this computer" — user clicks Allow, done. */
    CFStringRef key = kAXTrustedCheckOptionPrompt;
    CFDictionaryRef opts = CFDictionaryCreate(
        NULL,
        (const void **)&key, (const void **)&kCFBooleanTrue,
        1,
        &kCFTypeDictionaryKeyCallBacks,
        &kCFTypeDictionaryValueCallBacks
    );
    AXIsProcessTrustedWithOptions(opts);
    CFRelease(opts);

    /* Create the paste pipe.
     * Python3 writes 'P' → parent calls do_paste() with our Accessibility grant.
     * This sidesteps Python.framework's separate TCC identity for CGEventPost. */
    int paste_pipe[2];
    if (pipe(paste_pipe) != 0) {
        perror("[tacet] pipe");
        return 1;
    }
    char fd_str[16];
    snprintf(fd_str, sizeof(fd_str), "%d", paste_pipe[1]);
    setenv("TACET_PASTE_FD", fd_str, 1);

    /* cd into Resources so -m src.main resolves the src package */
    if (chdir(resources) != 0) {
        perror("[tacet] chdir");
        return 1;
    }

    /* Fork python3 as a child; this process (the bundle's main executable)
     * stays alive so macOS continues to attribute TCC requests to Tacet */
    pid_t pid = fork();
    if (pid < 0) { perror("[tacet] fork"); return 1; }

    if (pid == 0) {
        /* Child: close the read end, exec python3 */
        close(paste_pipe[0]);
        char *args[] = { python, "-m", "src.main", NULL };
        execv(python, args);
        perror("[tacet] execv");
        return 1;
    }

    /* Parent: close write end, then pump paste requests from python3.
     * Each 'P' byte means "clipboard is ready, fire Cmd+V now."
     * When the pipe closes (all write-end holders exited), drop into waitpid. */
    close(paste_pipe[1]);

    char buf[1];
    while (read(paste_pipe[0], buf, 1) > 0) {
        if (buf[0] == 'P') {
            do_paste();
        }
    }
    close(paste_pipe[0]);

    int status;
    waitpid(pid, &status, 0);
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}
