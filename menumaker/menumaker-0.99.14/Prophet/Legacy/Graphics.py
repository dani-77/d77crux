from Prophet.Legacy import App as _App, ConsoleApp as _ConsoleApp, X11App as _X11App
from Keywords import Keyword as Kw, Set as KwS
from Prophet.Categories import *


class xpcd(_App, _X11App):
    name = "XPCD"
    comment = "PhotoCD Viewer"
    keywords = KwS(Graphics, Photograph, Viewer)


class krita(_App, _X11App):
    name = "Krita KDE Bitmap Graphics Editor"
    comment = "Krita KDE Bitmap graphics editor"
    keywords = KwS(Graphics, RasterGraphics, KDE)


class ufraw(_App, _X11App):
    name = "Unidentified Flying RAW"
    comment = "Unidentified Flying RAW"
    keywords = KwS(Graphics, Photograph)
