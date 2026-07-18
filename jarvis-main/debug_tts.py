import sys
sys.path.insert(0, r'C:\Users\LENOVO\Downloads\jarvis-main\jarvis-main')
import os
import traceback
try:
    import edge_tts
    print('import-ok', edge_tts.__file__)
    import asyncio
    text = 'Jarvis online. I am ready to help you. What would you like me to do?'
    c = edge_tts.Communicate(text, voice='en-US-JennyNeural', rate='0%', volume='0%')
    print('communicate-created')
    asyncio.run(c.save(r'C:\Users\LENOVO\Downloads\jarvis-main\jarvis-main\test.wav'))
    print('saved', os.path.exists(r'C:\Users\LENOVO\Downloads\jarvis-main\jarvis-main\test.wav'))
except Exception as e:
    print('ERROR', repr(e))
    traceback.print_exc()
