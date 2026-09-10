local C={}
function C.json(v)
 local kind=type(v)
 if kind=='nil' then return 'null' end
 if kind=='boolean' or kind=='number' then return tostring(v) end
 if kind=='string' then
  return '"'..v:gsub('[%z\1-\31\\"]',function(c)
   local m={['"']='\\"',['\\']='\\\\',['\n']='\\n',['\r']='\\r',['\t']='\\t'}
   return m[c] or string.format('\\u%04x',c:byte())
  end)..'"'
 end
 assert(kind=='table','Unsupported JSON value')
 local array=true
 for k in pairs(v) do if type(k)~='number' then array=false;break end end
 local fields={}
 if array then
  for _,value in ipairs(v) do fields[#fields+1]=C.json(value) end
  return '['..table.concat(fields,',')..']'
 end
 for k,value in pairs(v) do fields[#fields+1]=C.json(k)..':'..C.json(value) end
 return '{'..table.concat(fields,',')..'}'
end
function C.write(path,value)
 local f=assert(io.open(path,'w'));f:write(C.json(value));f:close()
end
function C.setparam(tr,fx,param,value)
 assert(reaper.TrackFX_SetParam(tr,fx,param,value),'SetParam failed')
 local actual=reaper.TrackFX_GetParam(tr,fx,param)
 assert(math.abs(actual-value)<1e-5,'Plugin parameter readback mismatch: '..param)
end
function C.db(value) return 10^(value/20) end
function C.fx(tr,name)
 local index=reaper.TrackFX_AddByName(tr,name,false,-1)
 assert(index>=0,'Required stock plugin unavailable: '..name)
 assert(not reaper.TrackFX_GetOffline(tr,index),'Plugin is offline: '..name)
 return index
end
function C.clearfx(tr)
 for i=reaper.TrackFX_GetCount(tr)-1,0,-1 do reaper.TrackFX_Delete(tr,i) end
end
function C.decode64(text)
 local alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
 local value,bits,out=0,0,{}
 for char in text:gmatch('.') do
  if char~='=' then
   local n=assert(alphabet:find(char,1,true),'Invalid base64')-1
   value=(value<<6)|n;bits=bits+6
   if bits>=8 then
    bits=bits-8;out[#out+1]=string.char((value>>bits)&255)
    value=value&((1<<bits)-1)
   end
  end
 end
 return table.concat(out)
end
function C.limiter_true_peak(track,fx)
 local ok,encoded=reaper.TrackFX_GetNamedConfigParm(track,fx,'vst_chunk_program')
 assert(ok,'Cannot read ReaLimit state')
 local state=C.decode64(encoded)
 assert(#state==48 and string.unpack('<I4',state)==3,'ReaLimit state version changed; review profile compatibility')
 return string.unpack('<I4',state,5)==1
end
function C.inventory()
 assert(reaper.CountTracks(0)==1,'Requires one track')
 local tr=reaper.GetTrack(0,0);local master=reaper.GetMasterTrack(0)
 local items={}
 for i=0,reaper.CountTrackMediaItems(tr)-1 do
  local it=reaper.GetTrackMediaItem(tr,i);local tk=reaper.GetActiveTake(it)
  local src=reaper.GetMediaItemTake_Source(tk)
  local len=reaper.GetMediaSourceLength(src)
  assert(len>0,'Missing source')
  assert(reaper.GetMediaSourceNumChannels(src)==1,'Requires mono source')
  local rate=reaper.GetMediaItemTakeInfo_Value(tk,'D_PLAYRATE')
  assert(rate==1,'Time stretching is not allowed')
  assert(reaper.GetMediaItemTakeInfo_Value(tk,'D_PITCH')==0,'Pitch shift is not allowed')
  assert(reaper.GetTakeNumStretchMarkers(tk)==0,'Stretch markers are not allowed')
  local offset=reaper.GetMediaItemTakeInfo_Value(tk,'D_STARTOFFS')
  local duration=reaper.GetMediaItemInfo_Value(it,'D_LENGTH')
  assert(offset+duration<=len+1e-5,'Source overrun/loop detected')
  items[#items+1]={position=reaper.GetMediaItemInfo_Value(it,'D_POSITION'),length=duration,offset=offset,rate=rate,source_duration=len}
 end
 local plugins={}
 for _,track in ipairs({tr,master}) do
  for fx=0,reaper.TrackFX_GetCount(track)-1 do
   local _,name=reaper.TrackFX_GetFXName(track,fx,'')
   assert(not reaper.TrackFX_GetOffline(track,fx),'Offline plugin: '..name)
   local params={}
   for p=0,reaper.TrackFX_GetNumParams(track,fx)-1 do
    local _,pn=reaper.TrackFX_GetParamName(track,fx,p,'')
    local _,value=reaper.TrackFX_GetFormattedParamValue(track,fx,p,'')
    params[#params+1]={name=pn,value=value}
   end
   local truepeak=nil
   if name:find('ReaLimit',1,true) then truepeak=C.limiter_true_peak(track,fx) end
   plugins[#plugins+1]={name=name,enabled=reaper.TrackFX_GetEnabled(track,fx),parameters=params,true_peak=truepeak}
  end
 end
 return {items=items,plugins=plugins,duration=reaper.GetProjectLength(0),reaper_version=reaper.GetAppVersion()}
end
function C.render_settings(job,path,duration,dither)
 for key,value in pairs({PROJECT_SRATE=job.profile.render.sample_rate,PROJECT_SRATE_USE=1,
  RENDER_SRATE=job.profile.render.sample_rate,RENDER_CHANNELS=job.profile.render.channels,
  RENDER_SETTINGS=0,RENDER_BOUNDSFLAG=0,RENDER_STARTPOS=0,RENDER_ENDPOS=duration,
  RENDER_TAILFLAG=0,RENDER_TAILMS=0,RENDER_DITHER=dither and 1 or 0,RENDER_NORMALIZE=0,
  RENDER_ADDTOPROJ=0}) do reaper.GetSetProjectInfo(0,key,value,true) end
 local base=reaper.GetProjectPath('')
 assert(path:sub(1,#base+1)==base..'/','Render must stay inside the derived job')
 -- REAPER 7.79 batch rendering requires a resolved destination here.
 assert(reaper.GetSetProjectInfo_String(0,'RENDER_FILE',path,true))
 reaper.GetSetProjectInfo_String(0,'RENDER_PATTERN','',true)
 reaper.GetSetProjectInfo_String(0,'RENDER_FORMAT','ZXZhdxgAAA==',true)
 reaper.GetSetProjectInfo_String(0,'RENDER_FORMAT2','',true)
end
return C
