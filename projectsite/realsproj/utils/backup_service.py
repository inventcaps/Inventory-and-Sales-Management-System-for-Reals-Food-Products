"""
Windows Service for Reals Inventory Backup System
Run from projectsite/ directory:
  python realsproj/utils/backup_service.py install
  python realsproj/utils/backup_service.py start
  python realsproj/utils/backup_service.py stop
  python realsproj/utils/backup_service.py remove
"""

import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import sys
import os
import time
import subprocess
import schedule
from pathlib import Path

class RealsBackupService(win32serviceutil.ServiceFramework):
    _svc_name_ = "RealsInventoryBackup"
    _svc_display_name_ = "Reals Inventory Backup Service"
    _svc_description_ = "Automatic database backup service for Reals Inventory Management System"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)
        
        self.project_path = Path(__file__).resolve().parent.parent.parent
        self.manage_py = self.project_path / 'manage.py'

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_, ''))
        self.main()

    def main(self):
 
        schedule.every().day.at("02:00").do(self.run_backup)
        
        while True:
    
            if win32event.WaitForSingleObject(self.hWaitStop, 1000) == win32event.WAIT_OBJECT_0:
                break
            
            schedule.run_pending()
            time.sleep(60) 

    def run_backup(self):
        """Execute backup command"""
        try:
            servicemanager.LogInfoMsg(f"Running scheduled backup")
            
            result = subprocess.run([
                sys.executable,
                str(self.manage_py),
                'backup_database_python',
                '--email-notification'
            ], cwd=str(self.project_path), capture_output=True, text=True)
            
            if result.returncode == 0:
                servicemanager.LogInfoMsg("Backup completed successfully")
            else:
                servicemanager.LogErrorMsg(f"Backup failed: {result.stderr}")
                
        except Exception as e:
            servicemanager.LogErrorMsg(f"Backup error: {str(e)}")

if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(RealsBackupService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(RealsBackupService)
