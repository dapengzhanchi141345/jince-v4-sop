import os
print('local index.html size =', os.path.getsize(r'C:\Users\ASUS\jince-dashboard\index.html'))
print('remote index.html size =', 2997081)
print('match?', os.path.getsize(r'C:\Users\ASUS\jince-dashboard\index.html') == 2997081)
