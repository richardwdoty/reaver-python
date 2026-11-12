"""Generate synthetic Update Wire references using a temporary MATLAB source copy."""
import argparse, hashlib, json, subprocess
from pathlib import Path
import numpy as np
from scipy.io import savemat
from check_matlab_parity import ROOT, CONSTANTS, synthetic_cases

p=argparse.ArgumentParser()
p.add_argument('--matlab', required=True)
p.add_argument('--matlab-root', required=True, type=Path)
a=p.parse_args()
out=ROOT/'data/tmp/wire_reference';out.mkdir(parents=True,exist_ok=True)
source=(a.matlab_root/'REAVER GUI/updateWire.m').read_text()
patched=source.replace("'symmetric'", "'replicate'").replace('2*handles.constants.wireDilationThreshold','handles.constants.wireDilationThreshold')
# The output renderer is irrelevant to computational parity and requires a GUI.
patched=patched.replace('handles.image.CData = createNewBW2( handles ) ;','% Headless reference: display rendering omitted.')
(out/'updateWire.m').write_text(patched)
cases=np.empty(8,dtype=object)
for i,(name,image,params,channels) in enumerate(synthetic_cases()):
    mask=(image if image.ndim==2 else image[:,:,0])>100
    # Include a manually added connection and an erased region.
    mask[35:42,5:90]=True;mask[10:30,55:62]=False
    constants={v:float(getattr(params,k)) for k,v in CONSTANTS.items()}
    constants.update(survive=np.arange(4,9),born=np.arange(4,9))
    cases[i]=dict(name=name,binary=mask,constants=constants)
savemat(out/'inputs.mat',dict(cases=cases),do_compression=True)
fixture=ROOT/'tests/fixtures/wire_reference.mat'
q=lambda path:str(path.resolve()).replace('\\','/').replace("'","''")
script="""s=load('INPUT'); results=cell(size(s.cases));
for k=1:numel(s.cases)
 c=s.cases{k};h=struct();h.constants=c.constants;
 h.basePic.ySize=size(c.binary,1);h.basePic.xSize=size(c.binary,2);
 h.derivedPic.BW_2=logical(c.binary);
 h.derivedPic.branchpoints.line=struct('XData',[],'YData',[]);
 h.derivedPic.endpoints.line=struct('XData',[],'YData',[]);
 h=updateWire(h);results{k}=h.derivedPic;
end
cases=s.cases; matlab_version=version;save('OUTPUT','cases','results','matlab_version','-v7');
""".replace('INPUT',q(out/'inputs.mat')).replace('OUTPUT',q(fixture))
(out/'generate.m').write_text(script)
subprocess.run([a.matlab,'-wait','-nosplash','-nodesktop','-sd',str(out),'-batch',"run('"+q(out/'generate.m')+"')"],check=True)
fixture.with_suffix('.json').write_text(json.dumps(dict(original_sha256=hashlib.sha256(source.encode()).hexdigest(),changes=['symmetric to replicate','remove 2x dilation radius','omit GUI renderer'],source=str(a.matlab_root/'REAVER GUI/updateWire.m')),indent=2))
