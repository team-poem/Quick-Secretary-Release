import win32com.client
import os

hwp = win32com.client.Dispatch('HWPFrame.HwpObject')
hwp.RegisterModule('FilePathCheckDLL', 'SecurityModule')
hwp.XHwpWindows.Item(0).Visible = False

path = r'C:/Users/user/Desktop/pentong-20260416T024438Z-3-001/pentong/2025교육혁신처_20260409.hwp'
hwp.Open(path, 'HWP', 'forceopen:true')

text = hwp.GetTextFile('TEXT', '')
lines = text.split('\n')
print('서 라인 수:', len(lines))

for i, line in enumerate(lines):
    if 'AI' in line or '융합' in line or '연계' in line:
        s = max(0, i-1)
        e = min(len(lines), i+4)
        for j in range(s, e):
            print(str(j) + ': ' + repr(lines[j][:200]))
        print('---')

hwp.Quit()
