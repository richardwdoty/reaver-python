function display_reference(input_path, output_path, matlab_root)
addpath(fullfile(matlab_root,'REAVER GUI'));
s=load(input_path);results=cell(size(s.cases));
fig=figure('Visible','off');cleanup=onCleanup(@() close(fig));
gamma=uimenu(fig,'Tag','gammaAdjustItem','Checked','off');
for i=1:numel(s.cases)
 c=s.cases{i};h=struct();h.REAVER_Fig=fig;
 h.basePic.data=c.image;h.grayImage=size(c.image,3)==1;
 h.derivedPic.BW_2=logical(c.binary);h.derivedPic.wire=logical(c.wire);
 h.derivedPic.selectedColors=c.image;h.derivedPic.newWire=1;
 h.constants.selectedColors=logical(c.channels);
 h.miscValues.lineEdgeColor=uint8(c.edge);h.miscValues.centerLineColor=uint8(c.center);
 h.borderImage=zeros(size(c.binary),'uint8');h.borderImage(2:end-1,2:end-1)=1;
 if c.gamma;gamma.Checked='on';else;gamma.Checked='off';end
 results{i}=struct('overlay',createNewBW2(h),'wire',imdilate(logical(c.wire),strel('disk',2)));
end
save(output_path,'results','-v7');
end
