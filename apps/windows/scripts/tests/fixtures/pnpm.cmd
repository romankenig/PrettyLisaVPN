@echo off
echo test-stdout
echo test-stderr 1>&2
exit /b %PRETTYLISA_TEST_EXIT_CODE%
