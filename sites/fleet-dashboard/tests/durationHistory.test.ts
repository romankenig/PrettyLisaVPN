import { test } from "node:test";
import assert from "node:assert/strict";
import { readDurationHistory, durationSeries, type DurationHistory } from "../src/durationHistory.ts";
import { planFromSearch, withPlan, validateReportPlan, reportPlans } from "../src/reportPlan.ts";

function fixture(): DurationHistory {
  const dist = (counts: number[]) => ({bounds_seconds:[10,60,180,300,900], counts, samples:counts.reduce((a,b)=>a+b,0), shares:counts.map(v=>counts.some(Boolean) ? 100*v/counts.reduce((a,b)=>a+b,0) : null)});
  return {timezone:"GMT+3",plan:"ALL",generated_at:"2026-11-17T12:00:00Z",observed_from:"2026-11-15T12:00:00Z",from_date:"2026-11-14",through_date:"2026-11-17",points:[
    {date:"2026-11-14",partial:false,sessions:null,session_duration:null,time_to_silence:null,duration_unobserved_sessions:null,silence_unobserved_sessions:null},
    {date:"2026-11-15",partial:false,sessions:0,session_duration:dist([0,0,0,0,0,0]),time_to_silence:dist([0,0,0,0,0,0]),duration_unobserved_sessions:0,silence_unobserved_sessions:0},
    {date:"2026-11-16",partial:false,sessions:5,session_duration:dist([3,1,0,0,0,0]),time_to_silence:dist([0,0,1,0,1,0]),duration_unobserved_sessions:1,silence_unobserved_sessions:3},
    {date:"2026-11-17",partial:true,sessions:2,session_duration:dist([0,0,0,1,0,0]),time_to_silence:dist([0,0,0,0,0,0]),duration_unobserved_sessions:1,silence_unobserved_sessions:2},
  ]};
}
test("duration shares use each day's completed observations and preserve gaps and empty days",()=>{
  const data=readDurationHistory(fixture());
  assert.deepEqual(durationSeries(data,"session_duration",true)[0].values,[null,null,75,0]);
  assert.deepEqual(durationSeries(data,"session_duration",false)[0].values,[null,0,3,0]);
  assert.deepEqual(durationSeries(data,"time_to_silence",true)[2].values,[null,null,50,null]);
  assert.equal(new Set(durationSeries(data,"session_duration",true).map(s=>s.color)).size,6);
});
test("duration contract rejects mixed tariffs, dates, incomplete counts and fake zero shares",()=>{
  for (const mutate of [
    (d:DurationHistory)=>{d.points.splice(1,1)},
    (d:DurationHistory)=>{d.points[2].partial=true},
    (d:DurationHistory)=>{d.points[2].sessions=1},
    (d:DurationHistory)=>{d.points[2].session_duration!.shares[0]=60},
    (d:DurationHistory)=>{d.points[1].session_duration!.shares[0]=0},
    (d:DurationHistory)=>{d.points[0].duration_unobserved_sessions=0},
    (d:DurationHistory)=>{d.generated_at="2026-11-17T21:00:00Z"},
  ]) {const d=fixture();mutate(d);assert.throws(()=>readDurationHistory(d));}
});
test("tariff URLs preserve other filters and responses must match the selected tariff",()=>{
  for(const plan of reportPlans){
    assert.equal(planFromSearch(withPlan('/dashboard/?period=7d&node_ids=a',plan).split('?')[1]),plan);
    assert.doesNotThrow(()=>validateReportPlan({plan},plan));
  }
  assert.equal(withPlan('/dashboard/?plan=FREE&period=7d',"ALL"),'/dashboard/?period=7d');
  assert.equal(planFromSearch('?plan=untrusted'),"ALL");
  assert.throws(()=>validateReportPlan({plan:"ALL"},"FREE"));
  assert.throws(()=>validateReportPlan({},"FREE"));
  assert.doesNotThrow(()=>validateReportPlan({},"ALL"));
});
