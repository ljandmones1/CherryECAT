from building import *

cwd = GetCurrentDir()
path = [cwd + '/include']
src = []

LIBS    = []
LIBPATH = []
CPPDEFINES = []

src += Glob('src/ec_cmd.c')
src += Glob('src/ec_coe.c')
src += Glob('src/ec_common.c')
src += Glob('src/ec_datagram.c')
src += Glob('src/ec_foe.c')
src += Glob('src/ec_mailbox.c')
src += Glob('src/ec_master.c')
src += Glob('src/ec_netdev.c')
src += Glob('src/ec_perf.c')
src += Glob('src/ec_sii.c')
src += Glob('src/ec_slave.c')
src += Glob('src/ec_timestamp.c')
src += Glob('osal/ec_osal_rtthread.c')

group = DefineGroup('CherryECAT', src, depend = ['PKG_USING_CHERRYECAT'], LIBS = LIBS, LIBPATH=LIBPATH, CPPPATH = path, CPPDEFINES = CPPDEFINES)

Return('group')

