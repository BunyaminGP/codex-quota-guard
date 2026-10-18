"""Optional ntfy-compatible status messages; never reads a project webhook URL."""
import os
import urllib.request
import urllib.error


def notify(text):
    url = os.environ.get('CODEX_QUOTA_NOTIFY_URL', '')
    if not url.startswith(('https://', 'http://')):
        return False
    try:
        request = urllib.request.Request(url, data=text.encode('utf-8'),
                                         headers={'Title': 'codex-quota-guard',
                                                  'Content-Type': 'text/plain; charset=utf-8'})
        with urllib.request.urlopen(request, timeout=5):
            return True
    except (OSError, ValueError, urllib.error.URLError):
        return False
