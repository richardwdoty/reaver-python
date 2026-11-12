from pathlib import Path
import runpy
import numpy as np
import pytest
from scipy.io import loadmat
from reaver.app.params import SegmentationParams
from reaver.gui.segmentation_settings import (threshold_from_slider, threshold_from_text,
    slider_from_threshold, validated_settings, SETTING_LABELS)


@pytest.mark.parametrize('position,expected',[(0,0),(45,.045),(199,.199),(200,.2),(201,.204),(300,.6),(400,1)])
def test_matlab_slider_mapping(position,expected):
    assert threshold_from_slider(position)==expected
    assert slider_from_threshold(expected)==position


@pytest.mark.parametrize('text,expected',[('0.2005',.201),('0.0455',.046),('1',1),('0',0)])
def test_matlab_numeric_rounding(text,expected):
    assert threshold_from_text(text)==expected


@pytest.mark.parametrize('text',['nan','inf','-0.1','1.01','bad'])
def test_invalid_threshold(text):
    with pytest.raises(ValueError): threshold_from_text(text)


@pytest.mark.parametrize('field,value',[('averaging_filter_size',0),('averaging_filter_size',2.5),
    ('min_connected_component_area',-.1),('wire_dilation_threshold',1.5),('vessel_thickness_threshold','inf')])
def test_invalid_settings_leave_params_unchanged(field,value):
    params=SegmentationParams()
    values={n:getattr(params,n) for n in SETTING_LABELS};values[field]=value
    with pytest.raises(ValueError):validated_settings(params,values)
    assert params==SegmentationParams()


@pytest.mark.parametrize('index',range(6))
def test_nondefault_settings_matlab_parity(index):
    root=Path(__file__).resolve().parents[1]
    helper=runpy.run_path(str(root/'tools/check_matlab_parity.py'))
    reference=loadmat(root/'tests/fixtures/settings_reference.mat',simplify_cells=True)
    _,image,params,channels=list(helper['settings_cases']())[index]
    assert helper['compare'](image,params,channels,reference['results'][index])=={}
