return function(job,C)
 local before=C.inventory()
 local tr=reaper.GetTrack(0,0);local master=reaper.GetMasterTrack(0)
 reaper.SetMediaTrackInfo_Value(tr,'I_RECARM',0)
 reaper.SetMediaTrackInfo_Value(tr,'D_VOL',1)
 reaper.SetMediaTrackInfo_Value(master,'D_VOL',1)
 reaper.SetMediaTrackInfo_Value(tr,'I_FXEN',0)
 reaper.SetMediaTrackInfo_Value(master,'I_FXEN',0)
 reaper.GetSetProjectInfo_String(0,'RECORD_PATH','',true)
 local recovered=0
 if job.edit then
  local last=reaper.GetTrackMediaItem(tr,reaper.CountTrackMediaItems(tr)-1)
  local tk=reaper.GetActiveTake(last)
  local length=reaper.GetMediaItemInfo_Value(last,'D_LENGTH')
  local source_length=reaper.GetMediaSourceLength(reaper.GetMediaItemTake_Source(tk))
  local available=source_length-reaper.GetMediaItemTakeInfo_Value(tk,'D_STARTOFFS')-length
  if available>0 and available<=job.profile.timing.recover_tail_source_margin_seconds then
   recovered=math.min(available,job.profile.timing.recover_tail_seconds)
   reaper.SetMediaItemInfo_Value(last,'D_LENGTH',length+recovered)
   reaper.SetMediaItemInfo_Value(last,'D_FADEOUTLEN',job.profile.timing.fade_out_seconds)
   reaper.SetMediaItemInfo_Value(last,'D_FADEOUTLEN_AUTO',0)
  end
 end
 local inventory=C.inventory()
 C.render_settings(job,job.render_path,inventory.duration,false)
 reaper.Main_SaveProject(0,false)
 inventory.original_duration=before.duration
 inventory.recovered_tail_seconds=recovered
 return inventory
end
