"""Run unchanged MATLAB network measurements, retaining intermediate segments."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from scipy import ndimage as ndi
from scipy.io import loadmat,savemat
ROOT=Path(__file__).resolve().parents[1]


def synthetic_cases():
    base=np.zeros((64,80),bool)
    cases=[]
    def add(name,w,res=.65):
        cases.append(dict(name=name,wire=w.copy(),binary=ndi.binary_dilation(w,iterations=3),resolution=res))
    add('empty',base)
    w=base.copy();w[30,5:70]=True;add('straight_no_branches',w)
    w[5:55,35]=True;add('cross',w)
    add('cross_scaled',w,2.3)
    w=base.copy();w[20,10:60]=True;w[20:55,35]=True;add('tee',w)
    w=base.copy();w[5:50,35]=True
    for d in range(20):w[25+d,35+d]=w[25+d,35-d]=True
    add('diagonal_fork',w)
    w=base.copy();w[10,10:61]=w[50,10:61]=True;w[10:51,10]=w[10:51,60]=True
    w[30,0:11]=True;add('loop_branch_border',w)
    w=base.copy();w[10,0:30]=True;w[0:30,15]=True;w[42,45:80]=True;w[30:64,60]=True;add('disconnected_borders',w)
    w=base.copy();w[28:33,30]=True;w[30,28:33]=True;add('short_segments',w)
    w=base.copy();w[20:23,20:23]=True;w[21,5:45]=True;w[5:45,21]=True;add('thick_junction',w)
    return cases


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--matlab',required=True)
    p.add_argument('--matlab-root',required=True,type=Path)
    p.add_argument('--analysis',action='append',type=Path,default=[])
    p.add_argument('--snapshot',action='store_true')
    p.add_argument('--output',type=Path,default=ROOT/'data/tmp/measurement_reference')
    a=p.parse_args()
    if a.snapshot and a.analysis:p.error('Saved fixtures must be synthetic only')
    out=a.output;out.mkdir(parents=True,exist_ok=True)
    cases=synthetic_cases()
    for path in a.analysis:
        d=loadmat(path,simplify_cells=True,mat_dtype=True);v=d['derivedPic'];wire=v['wire']
        if hasattr(wire,'toarray'):wire=wire.toarray()
        cases.append(dict(name=str(path),binary=v['BW_2'],wire=wire,branchpoints=np.asarray(v['branchpoints']).reshape(-1,2),
            endpoints=np.asarray(v['endpoints']).reshape(-1,2),resolution=d.get('image_resolution',1.0)))
    savemat(out/'inputs.mat',dict(cases=np.array(cases,dtype=object)))
    q=lambda x:str(x).replace('\\','/').replace("'","''")
    cmd=f"addpath('{q(ROOT/'tests/matlab')}');measurement_reference('{q(out/'inputs.mat')}','{q(out/'reference.mat')}','{q(a.matlab_root)}')"
    subprocess.run([a.matlab,'-wait','-nosplash','-nodesktop','-sd',str(out),'-batch',cmd],check=True)
    sources={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (a.matlab_root/'Network Quantification').glob('*.m')}
    (out/'reference.json').write_text(json.dumps(dict(source_sha256=sources),indent=2))
    if a.snapshot:
        dest=ROOT/'tests/fixtures/measurement_reference.mat'
        dest.write_bytes((out/'reference.mat').read_bytes());dest.with_suffix('.json').write_bytes((out/'reference.json').read_bytes())
        dest.with_suffix('.csv').write_bytes((out/'reference.csv').read_bytes())
    r=loadmat(out/'reference.mat',simplify_cells=True)
    for case,result in zip(cases,r['results']):print(case['name'],result.get('metrics',result.get('error')),flush=True)


if __name__=='__main__':main()
