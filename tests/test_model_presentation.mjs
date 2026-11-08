import test from 'node:test';
import assert from 'node:assert/strict';
import {modelPresentation} from '../web/model-presentation.mjs';

test('floor view follows only a fresh settled measurement', () => {
  assert.equal(modelPresentation('floor', {fresh:true, estimate:{floor_id:'2',status:'settled'}}).floorId, '2');
  for (const state of [{fresh:false,estimate:{floor_id:'3',status:'settled'}}, {fresh:true,estimate:{floor_id:'3',status:'transition'}}]) {
    assert.equal(modelPresentation('floor', state).floorId, null);
  }
});
test('room view follows the actual winner, including all-floor searches', () => {
  const acoustic = {floor_id:null,positions:[{}],result:{status:'candidate',candidates:[{room_id:'nuc-2-yew',floor_ids:['2']} ]}};
  assert.deepEqual(modelPresentation('room',null,acoustic),{editable:false,floorId:'2',roomKey:'2/nuc-2-yew'});
  acoustic.result.candidates[0]={room_id:'nuc-3-studyroom',floor_ids:['3']};
  assert.equal(modelPresentation('room',null,acoustic).roomKey,'3/nuc-3-studyroom');
  acoustic.result.status='no_match';
  assert.equal(modelPresentation('room',null,acoustic).roomKey,'');
});
test('no accepted recording means no room focus; only 04 is editable', () => {
  const acoustic = {floor_id:'3',positions:[],result:{status:'candidate',candidates:[{room_id:'nuc-3-studyroom',floor_ids:['3']}]}};
  assert.equal(modelPresentation('room',null,acoustic).roomKey,'');
  assert.deepEqual(modelPresentation('model'),{editable:true});
  for (const view of ['intro','floor','room','gesture','results']) assert.equal(modelPresentation(view).editable,false);
});
