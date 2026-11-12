function measurement_reference(input_path,output_path,matlab_root)
addpath(fullfile(matlab_root,'Network Quantification'));
s=load(input_path); results=cell(size(s.cases));
csv_rows=table();
for k=1:numel(s.cases)
 c=s.cases{k};a=struct();
 a.derivedPic.BW_2=logical(c.binary);a.derivedPic.wire=logical(c.wire);
 if isfield(c,'branchpoints')
  a.derivedPic.branchpoints=c.branchpoints;a.derivedPic.endpoints=c.endpoints;
 else
  [r,col]=find(bwmorph(c.wire,'branchpoints'));a.derivedPic.branchpoints=[col,r];
  [r,col]=find(bwmorph(c.wire,'endpoints'));a.derivedPic.endpoints=[col,r];
 end
 a.imageSize=size(c.binary);a.image_resolution=c.resolution;
 file=fullfile(fileparts(output_path),'measurement_input.mat');save(file,'-struct','a');
 r=struct('input',a);
 [row,col]=find(c.wire,1,'first');
 if ~isempty(row);r.first_trace=bwtraceboundary(logical(c.wire),[row,col],'W');else;r.first_trace=zeros(0,2);end
 try
  [r.metrics,r.labels]=reaver_quantify_network(file);
  r.segments=skel_2_linesegs(a.derivedPic.wire,fliplr(a.derivedPic.branchpoints),fliplr(a.derivedPic.endpoints));
  r.tortuosity=rcind_seg_tortuosity(r.segments);
  [r.radii,r.index]=measure_segment_rad(r.segments,a.derivedPic.BW_2,fliplr(a.derivedPic.endpoints));
  r.error='';
  row=struct2table(r.metrics);row=addvars(row,{c.name},'Before',1,'NewVariableNames','image_name');
  csv_rows=[csv_rows;row];
 catch exception
  r.error=exception.message;
 end
 results{k}=r;
end
matlab_version=version;cases=s.cases;
save(output_path,'results','cases','matlab_version','-v7');
writetable(csv_rows,fullfile(fileparts(output_path),'reference.csv'));
end
