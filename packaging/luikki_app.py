"""What the installed app runs (`luikki.spec`).

With no command, or only options, it is `luikki app`. Any other `luikki`
command runs as it does from a checkout, which is how a build is checked:
`Luikki.exe flatten page.png` goes through every library and model the bundle
carries, without a window.
"""

import sys

from luikki.desktop import log_to_file

log_to_file()

from luikki.cli import main  # noqa: E402

arguments = sys.argv[1:]
if not arguments or arguments[0].startswith("-"):
    arguments = ["app", *arguments]
raise SystemExit(main(arguments))
