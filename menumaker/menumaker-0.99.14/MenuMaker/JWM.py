import MenuMaker
import Prophet.Legacy

from MenuMaker import indent, writeFullMenu

menuFile = "~/.jwmrc"


def _map(x):
    for d, s in (("&amp;", "&"), ("\'", "\"")):
        x = x.replace(s, d)
    return x


class Sep(object):

    def emit(self, level):
        return ['%s<Separator/>' % indent(level)]


class App(object):

    def emit(self, level):
        cmd = self.app.execmd
        if self.app.terminal:
            cmd = MenuMaker.terminal.runCmd(cmd)
        return [
            '%s<Program label="%s">%s</Program>' %
            (indent(level),
                _map(self.app.name),
                cmd
            )
        ]


class Menu(object):

    def emit(self, level):
        result = ['%s<Menu icon="folder.png" label="%s">' % (indent(level), _map(self.name))]
        for x in self:
            result += x.emit(level + 1)
        result.append('%s</Menu>' % indent(level))
        return result


class Root(object):

    def __init__(self, subs):
        super(Root, self).__init__(subs)

    def emit(self, level):
        if writeFullMenu:
            menu = [
                '<?xml version="1.0"?>',
                '<JWM>',
            ]
            menu += self.emitMenu(level)
            menu.append(defaultConfig)
            menu.append('</JWM>')
            return menu
        else:
            return self.emitMenu(level)

    def emitMenu(self, level):
        menu = ['<RootMenu onroot="12">']
        for x in self:
            menu += x.emit(level)
        sysmenu = [
            MenuMaker.Sep(),
            X('<Restart label="Restart" icon="restart.png"/>'),
            X('<Exit label="Exit" confirm="true" icon="quit.png"/>')
        ]
        for x in sysmenu:
            menu += x.emit(level)
        menu += ['</RootMenu>']
        return menu



class X(MenuMaker.Entry):

    def __init__(self, x):
        super(X, self).__init__()
        self.align = MenuMaker.Entry.StickBottom
        self.x = x

    def emit(self, level):
        return [indent(level) + self.x]


# Excerpt from /etc/system.jwmrc as of 2.3.7
defaultConfig = '''
    <!-- Options for program groups. -->
    <Group>
        <Option>tiled</Option>
        <Option>aerosnap</Option>
    </Group>
    <Group>
        <Class>Pidgin</Class>
        <Option>sticky</Option>
    </Group>
    <Group>
        <Name>xterm</Name>
        <Option>vmax</Option>
    </Group>
    <Group>
        <Name>xclock</Name>
        <Option>drag</Option>
        <Option>notitle</Option>
    </Group>

    <!-- Tray at the bottom. -->
    <Tray x="0" y="-1" autohide="off">

        <TrayButton icon="jwm-blue">root:1</TrayButton>
        <Spacer width="2"/>
        <TrayButton label="_">showdesktop</TrayButton>
        <Spacer width="2"/>

        <Pager labeled="true"/>

        <TaskList maxwidth="256"/>

        <Dock/>
        <Clock format="%H:%M"><Button mask="123">exec:xclock</Button></Clock>

    </Tray>

    <!-- Visual Styles -->
    <WindowStyle>
        <Font>Sans-9:bold</Font>
        <Width>4</Width>
        <Height>21</Height>
        <Corner>3</Corner>
        <Foreground>#FFFFFF</Foreground>
        <Background>#555555</Background>
        <Outline>#000000</Outline>
        <Opacity>0.5</Opacity>
        <Active>
            <Foreground>#FFFFFF</Foreground>
            <Background>#0077CC</Background>
            <Outline>#000000</Outline>
            <Opacity>1.0</Opacity>
        </Active>
    </WindowStyle>
    <TrayStyle group="true" list="all">
        <Font>Sans-9</Font>
        <Background>#333333</Background>
        <Foreground>#FFFFFF</Foreground>
        <Outline>#000000</Outline>
        <Opacity>0.75</Opacity>
    </TrayStyle>
    <TaskListStyle>
      <Font>Sans-9</Font>
      <Active>
        <Foreground>#FFFFFF</Foreground>
        <Background>#555555</Background>
      </Active>
      <Foreground>#FFFFFF</Foreground>
      <Background>#333333</Background>
    </TaskListStyle>
    <PagerStyle>
        <Outline>#000000</Outline>
        <Foreground>#555555</Foreground>
        <Background>#333333</Background>
        <Text>#FFFFFF</Text>
        <Active>
            <Foreground>#0077CC</Foreground>
            <Background>#004488</Background>
        </Active>
    </PagerStyle>
    <MenuStyle>
        <Font>Sans-9</Font>
        <Foreground>#FFFFFF</Foreground>
        <Background>#333333</Background>
        <Outline>#000000</Outline>
        <Active>
            <Foreground>#FFFFFF</Foreground>
            <Background>#0077CC</Background>
        </Active>
        <Opacity>0.85</Opacity>
    </MenuStyle>
    <PopupStyle>
        <Font>Sans-9</Font>
        <Foreground>#000000</Foreground>
        <Background>#999999</Background>
    </PopupStyle>

    <!-- Path where icons can be found.
         IconPath can be listed multiple times to allow searching
         for icons in multiple paths.
      -->
    <IconPath>
        /usr/share/icons/wm-icons/32x32-aquafusion
    </IconPath>
    <IconPath>
        /usr/local/share/jwm
    </IconPath>

    <!-- Virtual Desktops -->
    <!-- Desktop tags can be contained within Desktops for desktop names. -->
    <Desktops width="4" height="1">
        <!-- Default background. Note that a Background tag can be
              contained within a Desktop tag to give a specific background
              for that desktop.
         -->
        <Background type="solid">#111111</Background>
    </Desktops>

    <!-- Double click speed (in milliseconds) -->
    <DoubleClickSpeed>400</DoubleClickSpeed>

    <!-- Double click delta (in pixels) -->
    <DoubleClickDelta>2</DoubleClickDelta>

    <!-- The focus model (sloppy or click) -->
    <FocusModel>sloppy</FocusModel>

    <!-- The snap mode (none, screen, or border) -->
    <SnapMode distance="10">border</SnapMode>

    <!-- The move mode (outline or opaque) -->
    <MoveMode>opaque</MoveMode>

    <!-- The resize mode (outline or opaque) -->
    <ResizeMode>opaque</ResizeMode>

    <!-- Key bindings -->
    <Key key="Up">up</Key>
    <Key key="Down">down</Key>
    <Key key="Right">right</Key>
    <Key key="Left">left</Key>
    <Key key="h">left</Key>
    <Key key="j">down</Key>
    <Key key="k">up</Key>
    <Key key="l">right</Key>
    <Key key="Return">select</Key>
    <Key key="Escape">escape</Key>

    <Key mask="A" key="Tab">nextstacked</Key>
    <Key mask="A" key="F4">close</Key>
    <Key mask="A" key="#">desktop#</Key>
    <Key mask="A" key="F1">root:1</Key>
    <Key mask="A" key="F2">window</Key>
    <Key mask="A" key="F10">maximize</Key>
    <Key mask="A" key="Right">rdesktop</Key>
    <Key mask="A" key="Left">ldesktop</Key>
    <Key mask="A" key="Up">udesktop</Key>
    <Key mask="A" key="Down">ddesktop</Key>
'''