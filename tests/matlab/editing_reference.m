function editing_reference(input_path, output_path)
% Brush rasterization transcribed from REAVER_GUI figButtonMotion, followed
% by the temporary, explicitly corrected updateWire copy. Coordinates in
% the input are zero-based centers; MATLAB operates on one-based centers.
s = load(input_path);
results = cell(size(s.cases));
for k = 1:numel(s.cases)
    c = s.cases{k};
    binary = logical(c.binary);
    [row,col] = size(binary);
    masks = cell(size(c.strokes,1),1);
    for j = 1:size(c.strokes,1)
        stroke = double(c.strokes(j,:));
        x = stroke([1,3])' + 1;
        y = stroke([2,4])' + 1;
        if length(unique(x)) == 1 && length(unique(y)) == 1
            xi = x(1); yi = y(1);
        elseif length(unique(x)) > 1
            xi = linspace(min(x),max(x),50)';
            yi = interp1(x,y,xi);
        else
            yi = linspace(min(y),max(y),50)';
            xi = linspace(min(x),max(x),50)';
        end
        pts = unique(round([xi,yi]),'rows');
        pts((pts(:,1)<1)|(pts(:,1)>col)|(pts(:,2)<1)|(pts(:,2)>row),:) = [];
        painted = false(row,col);
        painted(sub2ind([row,col],pts(:,2),pts(:,1))) = true;
        radius = stroke(5)-1;
        if radius > 0
            painted = imdilate(painted,true(2*radius+1));
        end
        binary(painted) = logical(stroke(6));
        masks{j} = binary;
    end
    h = struct(); h.constants = c.constants;
    h.basePic.ySize = row; h.basePic.xSize = col;
    h.derivedPic.BW_2 = binary;
    h.derivedPic.branchpoints.line = struct('XData',[],'YData',[]);
    h.derivedPic.endpoints.line = struct('XData',[],'YData',[]);
    h = updateWire(h);
    results{k} = struct('masks',{masks},'updated',h.derivedPic);
end
cases = s.cases; matlab_version = version;
save(output_path,'cases','results','matlab_version','-v7');
end
