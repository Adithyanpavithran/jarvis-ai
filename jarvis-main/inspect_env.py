import sys
import site
import os
with open(r'C:\Users\LENOVO\Downloads\jarvis-main\jarvis-main\inspect_env.txt', 'w', encoding='utf-8') as f:
    f.write('executable=' + sys.executable + '\n')
    f.write('prefix=' + sys.prefix + '\n')
    f.write('version=' + sys.version + '\n')
    f.write('sitepackages=' + str(site.getsitepackages()) + '\n')
    try:
        import edge_tts
        f.write('edge_tts=' + str(edge_tts.__file__) + '\n')
    except Exception as e:
        f.write('edge_tts_error=' + repr(e) + '\n')
    try:
        import dotenv
        f.write('dotenv=' + str(dotenv.__file__) + '\n')
    except Exception as e:
        f.write('dotenv_error=' + repr(e) + '\n')
