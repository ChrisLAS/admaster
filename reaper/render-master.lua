-- Configure/save; the Python driver invokes REAPER's documented -renderproject.
return function(job,C)
 local tr=reaper.GetTrack(0,0)
 if job.gain_db then reaper.SetMediaTrackInfo_Value(tr,'D_VOL',C.db(job.gain_db)) end
 local master=reaper.GetMasterTrack(0)
 reaper.SetMediaTrackInfo_Value(master,'I_FXEN',job.prelimit and 0 or 1)
 reaper.SetMediaTrackInfo_Value(master,'D_VOL',job.prelimit and .06309573444801933 or 1)
 local inventory=C.inventory()
 local duration=job.plan.target_frames/job.profile.render.sample_rate
 assert(math.abs(inventory.duration-duration)<1e-8,'Project length differs from render bounds')
 C.render_settings(job,job.render_path,duration,true)
 reaper.GetSet_LoopTimeRange(true,false,0,duration,false)
 reaper.SetEditCurPos(0,false,false)
 reaper.GetSetProjectNotes(0,true,'Admaster profile '..job.profile.name..'. Original-speed edit; no stretching. See report.json, profile.toml and work/plan.json beside this project. Technical validation is separate from listening approval.')
 reaper.Main_SaveProject(0,false)
 return inventory
end
