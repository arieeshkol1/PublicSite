@echo off
REM Setup Made4Net WMS Login Page
REM Run this script on the frontend server

echo ========================================
echo Made4Net WMS - Login Page Setup
echo ========================================
echo.

cd C:\inetpub\made4net

echo Creating login page...

(
echo ^<!DOCTYPE html^>
echo ^<html^>
echo ^<head^>
echo     ^<title^>Made4Net WMS - Login^</title^>
echo     ^<meta charset="UTF-8"^>
echo     ^<meta name="viewport" content="width=device-width, initial-scale=1.0"^>
echo     ^<style^>
echo         body {
echo             font-family: Arial, sans-serif;
echo             background: linear-gradient^(135deg, #667eea 0%%, #764ba2 100%%^);
echo             display: flex;
echo             justify-content: center;
echo             align-items: center;
echo             height: 100vh;
echo             margin: 0;
echo         }
echo         .login-container {
echo             background: white;
echo             padding: 40px;
echo             border-radius: 10px;
echo             box-shadow: 0 10px 25px rgba^(0,0,0,0.2^);
echo             width: 350px;
echo         }
echo         h1 {
echo             text-align: center;
echo             color: #333;
echo             margin-bottom: 10px;
echo         }
echo         .subtitle {
echo             text-align: center;
echo             color: #666;
echo             margin-bottom: 30px;
echo             font-size: 14px;
echo         }
echo         .form-group {
echo             margin-bottom: 20px;
echo         }
echo         label {
echo             display: block;
echo             margin-bottom: 5px;
echo             color: #555;
echo             font-weight: bold;
echo         }
echo         input[type="text"], input[type="password"] {
echo             width: 100%%;
echo             padding: 10px;
echo             border: 1px solid #ddd;
echo             border-radius: 5px;
echo             box-sizing: border-box;
echo             font-size: 14px;
echo         }
echo         input[type="text"]:focus, input[type="password"]:focus {
echo             outline: none;
echo             border-color: #667eea;
echo         }
echo         button {
echo             width: 100%%;
echo             padding: 12px;
echo             background: #667eea;
echo             color: white;
echo             border: none;
echo             border-radius: 5px;
echo             font-size: 16px;
echo             cursor: pointer;
echo             font-weight: bold;
echo         }
echo         button:hover {
echo             background: #5568d3;
echo         }
echo         .footer {
echo             text-align: center;
echo             margin-top: 20px;
echo             color: #999;
echo             font-size: 12px;
echo         }
echo     ^</style^>
echo ^</head^>
echo ^<body^>
echo     ^<div class="login-container"^>
echo         ^<h1^>Made4Net WMS^</h1^>
echo         ^<p class="subtitle"^>Warehouse Management System^</p^>
echo         ^<form action="/login" method="post"^>
echo             ^<div class="form-group"^>
echo                 ^<label for="username"^>Username^</label^>
echo                 ^<input type="text" id="username" name="username" placeholder="Enter your username" required^>
echo             ^</div^>
echo             ^<div class="form-group"^>
echo                 ^<label for="password"^>Password^</label^>
echo                 ^<input type="password" id="password" name="password" placeholder="Enter your password" required^>
echo             ^</div^>
echo             ^<button type="submit"^>Login^</button^>
echo         ^</form^>
echo         ^<div class="footer"^>
echo             ^&copy; 2026 Made4Net - POC Environment
echo         ^</div^>
echo     ^</div^>
echo ^</body^>
echo ^</html^>
) > index.html

echo.
echo Login page created successfully!
echo.
echo Configuring IIS...
%windir%\system32\inetsrv\appcmd set site "Default Web Site" /physicalPath:C:\inetpub\made4net

echo.
echo Restarting IIS...
iisreset

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo You can now access the login page at:
echo   http://localhost
echo   http://^<your-elastic-ip^>
echo.
pause
