return function(job,C)
 local p=job.profile;local tr=reaper.GetTrack(0,0);local master=reaper.GetMasterTrack(0)
 C.clearfx(tr);C.clearfx(master)
 local eq=C.fx(tr,'ReaEQ (Cockos)')
 reaper.TrackFX_SetEQBandEnabled(tr,eq,0,0,true)
 assert(reaper.TrackFX_SetEQParam(tr,eq,0,0,0,p.eq.highpass_hz,false))
 for _,band in ipairs({1,4,5}) do reaper.TrackFX_SetEQBandEnabled(tr,eq,band,0,false) end
 for index,band in ipairs({{p.eq.body_hz,p.eq.body_db,p.eq.body_bandwidth_octaves},{p.eq.presence_hz,p.eq.presence_db,p.eq.presence_bandwidth_octaves}}) do
  for param,value in ipairs({band[1],C.db(band[2]),band[3]}) do
   assert(reaper.TrackFX_SetEQParam(tr,eq,2,index-1,param-1,value,false))
  end
 end
 reaper.TrackFX_SetNamedConfigParm(tr,eq,'renamed_name','ReaEQ - body and clarity')
 local comp=C.fx(tr,'ReaComp (Cockos)');local c=p.compressor
 local params={[0]=C.db(c.threshold_db),[1]=(c.ratio-1)/99,[2]=c.attack_ms/500,
  [3]=c.release_ms/5000,[4]=0,[6]=1,[7]=c.detector_highpass_hz/20000,
  [10]=0,[11]=1,[13]=c.rms_ms/100,[14]=c.knee_db/24,[15]=0,[16]=0}
 for param,value in pairs(params) do C.setparam(tr,comp,param,value) end
 reaper.TrackFX_SetNamedConfigParm(tr,comp,'renamed_name','ReaComp - soft dialogue control')
 local limit=C.fx(master,'ReaLimit (Cockos)')
 -- REAPER 7.79 exposes VST state but not a working TRUEPEAK named setter.
 -- Load only the approved 48-byte ReaLimit state through the documented API.
 assert(reaper.TrackFX_SetNamedConfigParm(master,limit,'vst_chunk_program',job.plugin_state),'Cannot load reference limiter state')
 assert(C.limiter_true_peak(master,limit),'Reference true-peak state readback failed')
 C.setparam(master,limit,0,(60+p.render.true_peak_db)/72)
 C.setparam(master,limit,1,(24+p.render.true_peak_db)/24)
 C.setparam(master,limit,2,p.limiter.release_normalized)
 reaper.TrackFX_SetNamedConfigParm(master,limit,'renamed_name','ReaLimit - safety ceiling')
 reaper.SetMediaTrackInfo_Value(tr,'I_FXEN',1)
 reaper.SetMediaTrackInfo_Value(master,'I_FXEN',1)
 reaper.SetMediaTrackInfo_Value(tr,'D_VOL',C.db(job.gain_db))
 reaper.SetMediaTrackInfo_Value(master,'D_VOL',1)
 reaper.GetSetMediaTrackInfo_String(tr,'P_NAME','Admaster - dialogue',true)
 return C.inventory()
end
