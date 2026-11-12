function save_mean_reference(output_path)
% Independent references for the single-precision mean in saveDataButton.
lengths = [0:300,1023,1024,1025,17439];
cases = cell(size(lengths));
for k=1:numel(lengths)
 n=lengths(k);
 values=2*sqrt(single(mod((1:n)'*37,1301)));
 cases{k}=struct('values',values,'expected',mean(values));
end
matlab_version=version;
save(output_path,'cases','matlab_version','-v7');
end
