import { test } from 'node:test';
import assert from 'node:assert/strict';
import { sessionResult } from '../web/session-result.mjs';

const state = () => ({floor_id: '3', stage: 'ready', positions: [{rt60_s: .387, snr_db: 76.7}], result: {status: 'candidate', candidates: [{room_id: 'nuc-3-studyroom', label: 'Study room, 3rd floor', floor_ids: ['3'], score: .9978}]}});
test('result comes from the winner, including when it is not the study room', () => {
  const s = state();
  assert.equal(sessionResult(s).title, 'Study room, 3rd floor');
  s.result.candidates[0] = {room_id: 'nuc-3-chemlab', label: 'Chemistry teaching laboratory', floor_ids: ['3'], score: .8};
  assert.equal(sessionResult(s).title, 'Chemistry teaching laboratory');
});
test('no measurement and no match cannot expose a room as the result', () => {
  assert.equal(sessionResult(null).top, null);
  const s = state(); s.result.status = 'no_match';
  assert.equal(sessionResult(s).top, null);
  assert.equal(sessionResult(s).title, 'No matching room');
  s.result.status = 'ambiguous';
  assert.match(sessionResult(s).status, /ambiguous/);
});
test('failed latest recording uses accepted metrics with an explanation', () => {
  const s = state(); s.stage = 'rejected'; s.last = {measurement: {rt60_s: 9}};
  assert.equal(sessionResult(s).rt60, '0.387 s');
  assert.match(sessionResult(s).note, /excluded/);
  s.floor_id = null;
  assert.equal(sessionResult(s).floor, '3');
  assert.equal(sessionResult(s).scope, 'All floors searched');
});
test('movement requires a fresh, connected, running detector', () => {
  const wifi = {connected:true, compatible:true, wifi:true, fresh:true, stage:'detecting', motion:true};
  assert.equal(sessionResult(null, wifi).motion, 'Movement detected');
  for (const field of ['connected', 'compatible', 'wifi', 'fresh']) assert.equal(sessionResult(null, {...wifi, [field]:false}).motion, 'Signal unavailable');
  assert.equal(sessionResult(null, {...wifi, motion:false}).motion, 'No movement detected');
  assert.equal(sessionResult(null, {...wifi, motion:null}).motion, 'Motion unknown');
  assert.equal(sessionResult(null, {...wifi, stage:'calibrating'}).motion, 'Calibrating');
});
