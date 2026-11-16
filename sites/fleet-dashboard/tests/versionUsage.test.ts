import { test } from "node:test";
import assert from "node:assert/strict";
import { readVersionReport, versionSeries, type VersionReport } from "../src/versionUsage.ts";
import { reportPage } from "../src/reportRoutes.ts";

function fixture(): VersionReport {
  const points = Array.from({ length: 31 }, (_, i) => ({date:new Date(Date.UTC(2026, 9, 17+i)).toISOString().slice(0,10),partial:i===30,platforms:i<29?null:i===29?{}:{ANDROID:{users:{"0.28.1":1,"0.28.2":2,UNKNOWN:1},devices:{"0.28.1":1,"0.28.2":3,UNKNOWN:1},active_users:3},CHROME_EXTENSION:{users:{"0.4.1":1},devices:{"0.4.1":1},active_users:1}}}));
  return { schema:1,timezone:"GMT+3",generated_at:"2026-11-16T12:00:00Z",collection_started_at:"2026-11-15T12:00:00Z",from_date:points[0].date,through_date:points[30].date,points };
}
test("daily version users/shares keep platforms and UNKNOWN separate and preserve gaps", () => {
  const data = readVersionReport(fixture()), counts = versionSeries(data,"ANDROID",false), shares = versionSeries(data,"ANDROID",true);
  assert.deepEqual(counts.map(r=>r.name),["0.28.1","0.28.2","UNKNOWN"]);
  assert.deepEqual(shares.map(r=>r.values[30]),[25,50,25]);
  assert.equal(counts[0].values[28],null);assert.equal(counts[0].values[29],0);assert.equal(shares[0].values[29],null);
  assert.equal(counts[2].color,"#9c9c9c");assert.equal(new Set(counts.map(r=>r.color)).size,3);
  assert.deepEqual(versionSeries(data,"CHROME_EXTENSION",false).map(r=>r.name),["0.4.1"]);
  assert.deepEqual(versionSeries(data,"WINDOWS",false),[]);
  assert.equal(reportPage("/dashboard/app-versions/"),"versions");
});
test("invalid days, counts, platform IDs and incomplete contracts are rejected", () => {
  for (const mutate of [
    (v:VersionReport)=>{v.points[30].partial=false;},
    (v:VersionReport)=>{v.points[29].date=v.points[28].date;},
    (v:VersionReport)=>{v.points[30].platforms!.ANDROID.users["0.28.2"]=4;},
    (v:VersionReport)=>{v.points[30].platforms!.ANDROID.active_users=8;},
    (v:VersionReport)=>{v.generated_at="bad";},
  ]) {const value=fixture();mutate(value);assert.throws(()=>readVersionReport(value));}
});
