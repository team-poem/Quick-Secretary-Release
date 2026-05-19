import win32com.client
import os

hwp = win32com.client.Dispatch('HWPFrame.HwpObject')
hwp.RegisterModule('FilePathCheckDLL', 'SecurityModule')
hwp.XHwpWindows.Item(0).Visible = False

path = r'C:\Users\user\Desktop\pentong-20260416T024438Z-3-001\pentong\2025교육혁신처_20260409.hwp'
hwp.Open(path, 'HWP', 'forceopen:true')

text = hwp.GetTextFile('TEXT', '')
lines = text.split('\n')

# 1. [별표 5] 전체 섹션 (라인 4200~4600 구간)
print('='*60)
print('=== [별표 5] 구버전 AI공학 섹션 (라인 4200~4600) ===')
print('='*60)
for i in range(4200, min(4600, len(lines))):
    print(f'{i}: {repr(lines[i][:400])}')

# 2. 신버전 [별표 5] AI공학 섹션 (라인 18400~18700)
print('\n' + '='*60)
print('=== 신버전 AI공학 섹션 (라인 18400~18700) ===')
print('='*60)
for i in range(18400, min(18700, len(lines))):
    print(f'{i}: {repr(lines[i][:400])}')

hwp.Quit()
