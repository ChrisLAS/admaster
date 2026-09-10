return function(job,C)
 local tr=reaper.GetTrack(0,0);local timing=job.plan
 local xf=job.profile.timing.crossfade_seconds
 local sr=job.profile.render.sample_rate
 for i=#timing.cuts,1,-1 do
  local a,b=timing.cuts[i].start,timing.cuts[i]['end']
  local xf=math.min(xf,(b-a)/2)
  local item=nil
  for k=0,reaper.CountTrackMediaItems(tr)-1 do
   local it=reaper.GetTrackMediaItem(tr,k)
   local pos=reaper.GetMediaItemInfo_Value(it,'D_POSITION')
   if pos<a and pos+reaper.GetMediaItemInfo_Value(it,'D_LENGTH')>b then item=it;break end
  end
  assert(item,'Cut must be contained in one item')
  local mid=assert(reaper.SplitMediaItem(item,a+xf/2),'Left split failed')
  local right=assert(reaper.SplitMediaItem(mid,b-xf/2),'Right split failed')
  reaper.DeleteTrackMediaItem(tr,mid)
  reaper.SetMediaItemInfo_Value(item,'D_FADEOUTLEN',0)
  reaper.SetMediaItemInfo_Value(item,'D_FADEOUTLEN_AUTO',xf)
  reaper.SetMediaItemInfo_Value(item,'C_FADEOUTSHAPE',0)
  reaper.SetMediaItemInfo_Value(right,'D_FADEINLEN',0)
  reaper.SetMediaItemInfo_Value(right,'D_FADEINLEN_AUTO',xf)
  reaper.SetMediaItemInfo_Value(right,'C_FADEINSHAPE',0)
  for k=0,reaper.CountTrackMediaItems(tr)-1 do
   local it=reaper.GetTrackMediaItem(tr,k)
   local pos=reaper.GetMediaItemInfo_Value(it,'D_POSITION')
   if pos>=b-xf/2-1e-8 then reaper.SetMediaItemInfo_Value(it,'D_POSITION',pos-(b-a)) end
  end
 end
 local head=timing.head_frames/sr;local tail=timing.tail_frames/sr
 local first=reaper.GetTrackMediaItem(tr,0)
 if head>0 then
  local tk=reaper.GetActiveTake(first)
  reaper.SetMediaItemTakeInfo_Value(tk,'D_STARTOFFS',reaper.GetMediaItemTakeInfo_Value(tk,'D_STARTOFFS')+head)
  reaper.SetMediaItemInfo_Value(first,'D_LENGTH',reaper.GetMediaItemInfo_Value(first,'D_LENGTH')-head)
  for i=1,reaper.CountTrackMediaItems(tr)-1 do
   local it=reaper.GetTrackMediaItem(tr,i)
   reaper.SetMediaItemInfo_Value(it,'D_POSITION',reaper.GetMediaItemInfo_Value(it,'D_POSITION')-head)
  end
 end
 local last=reaper.GetTrackMediaItem(tr,reaper.CountTrackMediaItems(tr)-1)
 if tail>0 then reaper.SetMediaItemInfo_Value(last,'D_LENGTH',reaper.GetMediaItemInfo_Value(last,'D_LENGTH')-tail) end
 if job.edit then
  reaper.SetMediaItemInfo_Value(first,'D_FADEINLEN',job.profile.timing.fade_in_seconds)
  reaper.SetMediaItemInfo_Value(last,'D_FADEOUTLEN',job.profile.timing.fade_out_seconds)
 end
 -- Reconcile only sub-sample render rounding at the quiet end, never truncate speech.
 local desired=timing.target_frames/sr
 local delta=desired-reaper.GetProjectLength(0)
 assert(math.abs(delta)<=1/sr+1e-8,'Timing plan did not reach requested duration')
 if delta~=0 then reaper.SetMediaItemInfo_Value(last,'D_LENGTH',reaper.GetMediaItemInfo_Value(last,'D_LENGTH')+delta) end
 for i=0,reaper.CountTrackMediaItems(tr)-1 do
  local it=reaper.GetTrackMediaItem(tr,i);local tk=reaper.GetActiveTake(it)
  reaper.SetMediaItemTakeInfo_Value(tk,'D_PLAYRATE',1)
  reaper.SetMediaItemTakeInfo_Value(tk,'D_PITCH',0)
  reaper.SetMediaItemTakeInfo_Value(tk,'B_PPITCH',0)
  reaper.SetMediaItemTakeInfo_Value(tk,'I_PITCHMODE',-1)
  reaper.SetMediaItemInfo_Value(it,'B_LOOPSRC',0)
 end
 return C.inventory()
end
