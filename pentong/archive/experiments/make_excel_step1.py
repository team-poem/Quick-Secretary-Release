import win32com.client
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

hwp = win32com.client.Dispatch("HWPFrame.HwpObject")
hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")
hwp.XHwpWindows.Item(0).Visible = False
path = r'C:\Users\user\Desktop\pentong-20260416T024438Z-3-001\pentong\2025\uad50\uc721\ud601\uc2e0\uccb4_20260409.hwp'
hwp.Open(path, "HWP", "forceopen:true")
text = hwp.GetTextFile("TEXT", "")
hwp.Quit()
print("HWP text extracted, total lines:", len(text.split("
")))