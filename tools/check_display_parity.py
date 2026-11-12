"""Compare fresh MATLAB overlay/wire pixels, using synthetic and optional real saved images."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from scipy.io import loadmat,savemat
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from reaver.io.results import load_analysis
from reaver.app.image_state import ReaverImageState,BaseImage,DerivedLayers
from reaver.app.display_settings import DisplaySettings
from reaver.gui.image_viewer import render_view


def cases(analyses=()):
    rng=np.random.default_rng(119)
    binary=np.zeros((70,90),bool);binary[15:40,:]=True;binary[:,35:55]=True
    wire=np.zeros_like(binary);wire[27,:]=True;wire[:,45]=True
    states=[]
    for shape in ((70,90,3),(70,90,1)):
        image=rng.integers(30,160,shape,dtype=np.uint8)
        states.append(ReaverImageState('synthetic',Path('synthetic'),base_image=BaseImage(Path('synthetic'),image),
            derived_layers=DerivedLayers(bw_2=binary,wire=wire)))
    states.extend(load_analysis(p) for p in analyses)
    for state in states:
        for gamma in (False,True):
            for colors in (((0,255,0),(255,255,255)),((129,0,53),(0,130,205))):
                settings=DisplaySettings(gamma_adjust=gamma,edge_line_color=colors[0],center_line_color=colors[1])
                yield state,settings,(True,False,True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matlab',required=True);parser.add_argument('--matlab-root',required=True,type=Path)
    parser.add_argument('--analysis',type=Path,action='append',default=[])
    parser.add_argument('--snapshot',action='store_true')
    args=parser.parse_args()
    if args.snapshot and args.analysis:parser.error('Synthetic snapshots only')
    out=ROOT/'data/tmp/display_parity';out.mkdir(exist_ok=True,parents=True)
    suite=list(cases(args.analysis));inputs=[];hashes={}
    for state,settings,channels in suite:
        inputs.append(dict(image=state.base_image.data,binary=state.derived_layers.bw_2,wire=state.derived_layers.wire,
            channels=channels,gamma=settings.gamma_adjust,edge=settings.edge_line_color,center=settings.center_line_color))
        if state.path.exists():hashes[str(state.path)]=hashlib.sha256(state.path.read_bytes()).hexdigest()
    for path in args.analysis:hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    savemat(out/'inputs.mat',dict(cases=np.array(inputs,dtype=object)))
    quote=lambda p:str(p).replace('\\','/').replace("'","''")
    cmd=f"addpath('{quote(ROOT/'tests/matlab')}');display_reference('{quote(out/'inputs.mat')}','{quote(out/'reference.mat')}','{quote(args.matlab_root)}')"
    subprocess.run([args.matlab,'-wait','-nosplash','-nodesktop','-sd',str(out),'-batch',cmd],check=True)
    refs=loadmat(out/'reference.mat',simplify_cells=True)['results']
    for (state,settings,channels),ref in zip(suite,refs):
        for mode,key in [('overlay','overlay'),('wire_frame','wire')]:
            actual=render_view(state,mode,channels,settings=settings)
            np.testing.assert_array_equal(actual,ref[key] if key=='overlay' else ref[key].astype(np.uint8)*255)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    report=dict(cases=len(suite),pixel_parity='exact',original_hashes=hashes)
    (out/'report.json').write_text(json.dumps(report,indent=2))
    if args.snapshot:
        (ROOT/'tests/fixtures/display_reference.mat').write_bytes((out/'reference.mat').read_bytes())
    print(report['cases'],'display cases EXACT',flush=True)


if __name__=='__main__':main()
