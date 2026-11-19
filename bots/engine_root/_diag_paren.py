import re
src=open('E:/GoldstrategyEngine/_night_族2区间反转.py',encoding='utf-8').read()
depth=0; in_str=None; unclosed=[]
for ln_no,ln in enumerate(src.splitlines(),1):
    i=0; n=len(ln); bs=chr(92)
    while i<n:
        ch=ln[i]
        if in_str:
            if ch==bs and i+1<n: i+=2; continue
            if ch==in_str: in_str=None
            i+=1; continue
        if ch in ('"',"'"):
            in_str=ch; i+=1; continue
        if ch=='#': break
        if ch=='(':
            depth+=1; unclosed.append((ln_no,depth))
        elif ch==')':
            if depth>0:
                depth-=1; unclosed.pop()
        i+=1
    in_str=None
print("final depth",depth)
for u in unclosed[-8:]: print(u)
