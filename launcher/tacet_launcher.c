#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
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
 *   3. cd into Resources so python3 -m src.main finds the src package
 *   4. Fork python3 from the bundled venv, wait for it to exit
 */

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
        char *args[] = { python, "-m", "src.main", NULL };
        execv(python, args);
        perror("[tacet] execv");
        return 1;
    }

    int status;
    waitpid(pid, &status, 0);
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}
