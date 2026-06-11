import subprocess
import re
import sys

ports = [8001,8002,8003,8004,8005]
out = subprocess.check_output(['netstat','-ano'], text=True, shell=True)
for line in out.splitlines():
    for p in ports:
        if f':{p} ' in line or f':{p}\r' in line or f':{p}\n' in line:
            parts = re.split(r'\s+', line.strip())
            if parts:
                pid = parts[-1]
                try:
                    print(f'Killing PID {pid} listening on port {p}')
                    subprocess.run(['taskkill','/PID',pid,'/F'], check=True)
                except Exception as e:
                    print('Failed to kill', pid, e)

print('Done')
