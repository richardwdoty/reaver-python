function generate_reference(input_path, output_path, matlab_root)
% Run the original GUI algorithm without creating graphical objects.
addpath(fullfile(matlab_root, 'REAVER GUI'));
s = load(input_path);
results = cell(size(s.cases));
for k = 1:numel(s.cases)
    c = s.cases{k};
    h = struct();
    h.basePic.data = c.image;
    h.basePic.ySize = size(c.image,1);
    h.basePic.xSize = size(c.image,2);
    h.constants = c.constants;
    selected = c.image;
    if size(selected,3) == 1
        h.derivedPic.grey = double(selected);
    else
        selected(:,:,~logical(c.channels)) = 0;
        h.derivedPic.grey = double(rgb2gray(selected));
    end
    h.derivedPic.branchpoints.line = struct('XData',[],'YData',[],'Visible','off');
    h.derivedPic.endpoints.line = struct('XData',[],'YData',[],'Visible','off');
    h = segmentImage(h);
    results{k} = h.derivedPic;
end
ops = {'fill','bridge','thin','spur','clean','majority','branchpoints','endpoints'};
morphology = struct();
for k=1:numel(ops)
    morphology.(ops{k}) = bwmorph(logical(s.morph_input),ops{k},1);
end
matlab_version = version;
save(output_path, 'results', 'morphology', 'matlab_version', '-v7');
end
