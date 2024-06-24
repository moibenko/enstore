#!/usr/bin/env python
import subprocess

def fill_analysis(src_spec_dir, src_list, out_file):
    cnt = 0
    for f in src_list:
        print(f, cnt)
        with open("{}/{}.spec".format(src_spec_dir, f), 'r') as rf:
            while True:
                l = rf.readline()
                l = l.replace("a = Analysis(", "f{} = Analysis(".format(cnt))
                if cnt > 0 and l.find("#") == 0:
                    # skip comment line
                    continue
                out_file.write(l)
                if l.find(")") == 0:
                    break
                if not l:
                    break
        cnt += 1

def fill_merge(src_list, out_file):
    cnt = 0
    s = []
    s.append("MERGE(")
    for f in src_list:
        s.append("(f{}, '{}', '{}'),".format(cnt, f, f))
        cnt += 1
    s.append(")")
    for l in s:
        out_file.write("{}\n".format(l))

def fill_pyz_exe(src_spec_dir, src_list, out_file):
    cnt = 0
    for f in src_list:
        with open("{}/{}.spec".format(src_spec_dir, f), 'r') as rf:
            while True:
                l = rf.readline()
                if l.find(")") == 0:
                    break
            while True:
                l = rf.readline()
                l = l.replace("pyz", "pyz{}".format(cnt))
                l = l.replace("exe ", "exe{} ".format(cnt))
                l = l.replace("a.pure", "f{}.pure".format(cnt))
                l = l.replace("a.scripts", "f{}.scripts".format(cnt))
                if cnt > 0 and l.find("#") == 0:
                    # skip comment line                                                                                     
                    continue
                out_file.write(l)
                if l.find(")") == 0:
                    break
                if not l:
                    break
            cnt += 1

def fill_collect(src_list, collection_name, out_file):
    cnt = 0
    s = []
    s.append("coll = COLLECT(")
    for f in src_list:
        s.append("    exe{},".format(cnt))
        s.append("    f{}.binaries,".format(cnt))
        s.append("    f{}.datas,".format(cnt))
        cnt += 1
    s.append("    strip=False,")
    s.append("    upx=True,")
    s.append("    upx_exclude=[],")
    s.append("    name='{}')".format(collection_name))
    for l in s:
        out_file.write("{}\n".format(l))
        
import sys
spec_dir = "/home/enstore/enstore_p2p3_stage2_src_only_no_cache/enstore/pyinstaller/specs/"
src_list = []

with open('spec_list', 'r') as f:
    for line in f.readlines():
        src_list.append(line.strip())

#sys.exit()

with open("specs/enstore_sbin.spec", "w") as of:
    fill_analysis(spec_dir, src_list, of)
    fill_merge(src_list, of)
    fill_pyz_exe(spec_dir, src_list, of)
    fill_collect(src_list, 'sbin', of)

    
