@echo off
chcp 65001 >nul
echo ==========================================
echo   뚝딱비서 빌드
echo ==========================================
echo.

echo [1/3] 필수 패키지 설치 중...
pip install pyinstaller openpyxl pywin32 windnd Pillow --quiet 2>nul

echo [2/3] 빌드 중...
python -m PyInstaller pentong_chat.spec --noconfirm --clean

echo.
if exist "dist\뚝딱비서.exe" (
    echo [OK] 빌드 성공!
    echo.
    echo   실행 파일: dist\뚝딱비서.exe
    for %%A in ("dist\뚝딱비서.exe") do echo   파일 크기: %%~zA bytes
    echo.
    echo 배포: 뚝딱비서.exe 파일 하나만 전달하면 됩니다.
) else (
    echo [FAIL] 빌드 실패. 위 로그를 확인하세요.
)

echo.
pause
