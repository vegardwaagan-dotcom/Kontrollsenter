-- Kontrollsenter Stats – samler statistikk per karakter som Kontrollsenter (PC) og Android-appen viser.
-- WoW skriver SavedVariables til disk når du logger ut eller skriver /reload. /ks viser tallene i spillet.
-- Bare lesing av spillets egne hendelser – ingen automatisering, ingen endring av spillet.

local ADDON = ...
local f = CreateFrame("Frame")
local C                      -- denne karakterens tabell
local session                -- økten som pågår nå
local playedBase, playedLevelBase, playedAt = nil, nil, nil   -- fra TIME_PLAYED_MSG
local lastAttacker
local combatStart
local MAXNAMES = 250

local function now() return time() end

local function bump(t, key, n)
  if not key or key == "" then return end
  t[key] = (t[key] or 0) + (n or 1)
  -- hold tabellen liten: fjern de minste når den blir for stor
  local count = 0
  for _ in pairs(t) do count = count + 1 end
  if count > MAXNAMES then
    local smallest, sk = math.huge, nil
    for k, v in pairs(t) do if v < smallest then smallest, sk = v, k end end
    if sk then t[sk] = nil end
  end
end

local function playedNow()
  if not playedBase then return C and C.played or 0, C and C.played_level or 0 end
  local d = GetTime() - playedAt
  return math.floor(playedBase + d), math.floor(playedLevelBase + d)
end

local function ensureChar()
  KontrollsenterStatsDB = KontrollsenterStatsDB or { version = 1, chars = {} }
  local db = KontrollsenterStatsDB
  db.chars = db.chars or {}
  local key = GetRealmName() .. "-" .. UnitName("player")
  db.chars[key] = db.chars[key] or { first_seen = now() }
  C = db.chars[key]
  C.name, C.realm = UnitName("player"), GetRealmName()
  C.class = select(2, UnitClass("player"))
  C.class_name = UnitClass("player")
  C.race = UnitRace("player")
  C.faction = UnitFactionGroup and UnitFactionGroup("player") or nil
  C.level = UnitLevel("player")
  C.dist = C.dist or { walk = 0, mount = 0, swim = 0, taxi = 0, fly = 0 }
  C.kills_by = C.kills_by or {}
  C.killers = C.killers or {}
  C.zones = C.zones or {}
  C.levels = C.levels or {}
  C.level_time = C.level_time or {}
  for _, k in ipairs({ "kills", "deaths", "quests", "xp", "gold_in", "gold_out", "dmg", "heal", "max_hit",
                       "max_heal", "jumps", "combat_time", "sessions", "crits" }) do
    C[k] = C[k] or 0
  end
  C.sessions = C.sessions + 1
  C.money = GetMoney()
  C.xp_now, C.xp_max = UnitXP("player"), UnitXPMax("player")
  db.addon_version = GetAddOnMetadata and GetAddOnMetadata(ADDON, "Version") or nil
end

local function save()
  if not C then return end
  local total, lvl = playedNow()
  C.played, C.played_level = total, lvl
  C.last_seen = now()
  C.level = UnitLevel("player")
  C.money = GetMoney()
  if session then
    session.len = now() - session.start
    C.last_session = session
  end
  if GetPVPLifetimeStats then
    local hk = GetPVPLifetimeStats()
    if type(hk) == "number" then C.hk = hk end
  end
  C.zone = GetRealZoneText and GetRealZoneText() or nil
end

-- Spilletid: addonen BER IKKE om /played (RequestTimePlayed er låst for addons i nyere WoW og gir
-- «blocked from an action only available to the Blizzard UI»). WoW sender TIME_PLAYED_MSG selv ved
-- innlogging og når du skriver /played – mellom svarene regnes tiden videre her.

-- distanse: fart (yards/s) × tid, sortert etter hvordan du beveger deg
local acc = 0
f:SetScript("OnUpdate", function(_, elapsed)
  acc = acc + elapsed
  if acc < 0.25 or not C then return end
  local dt = acc; acc = 0
  local speed = GetUnitSpeed("player") or 0
  if speed <= 0 then return end
  local yards = speed * dt
  local kind = "walk"
  if UnitOnTaxi and UnitOnTaxi("player") then kind = "taxi"
  elseif IsFlying and IsFlying() then kind = "fly"
  elseif IsSwimming and IsSwimming() then kind = "swim"
  elseif IsMounted and IsMounted() then kind = "mount" end
  C.dist[kind] = (C.dist[kind] or 0) + yards
  if session then session.dist = session.dist + yards end
end)

if hooksecurefunc and JumpOrAscendStart then
  hooksecurefunc("JumpOrAscendStart", function()
    if C and not (UnitOnTaxi and UnitOnTaxi("player")) then C.jumps = C.jumps + 1 end
  end)
end

local function onCombatLog()
  local _, sub, _, srcGUID, srcName, _, _, dstGUID, dstName = CombatLogGetCurrentEventInfo()
  local me = UnitGUID("player")
  if sub == "PARTY_KILL" and srcGUID == me then
    C.kills = C.kills + 1
    bump(C.kills_by, dstName)
    if session then session.kills = session.kills + 1 end
    return
  end
  if srcGUID == me or (UnitGUID("pet") and srcGUID == UnitGUID("pet")) then
    local amount, crit
    if sub == "SWING_DAMAGE" then
      amount = select(12, CombatLogGetCurrentEventInfo())
      crit = select(18, CombatLogGetCurrentEventInfo())
    elseif sub == "SPELL_DAMAGE" or sub == "RANGE_DAMAGE" or sub == "SPELL_PERIODIC_DAMAGE" then
      amount = select(15, CombatLogGetCurrentEventInfo())
      crit = select(21, CombatLogGetCurrentEventInfo())
    elseif sub == "SPELL_HEAL" or sub == "SPELL_PERIODIC_HEAL" then
      local heal = select(15, CombatLogGetCurrentEventInfo()) or 0
      local over = select(16, CombatLogGetCurrentEventInfo()) or 0
      local eff = math.max(0, heal - over)
      C.heal = C.heal + eff
      if eff > C.max_heal then C.max_heal = eff; C.max_heal_spell = select(13, CombatLogGetCurrentEventInfo()) end
      return
    end
    if type(amount) == "number" and amount > 0 then
      C.dmg = C.dmg + amount
      if crit then C.crits = C.crits + 1 end
      if session then session.dmg = session.dmg + amount end
      if amount > C.max_hit then
        C.max_hit = amount
        C.max_hit_spell = sub == "SWING_DAMAGE" and "Melee" or select(13, CombatLogGetCurrentEventInfo())
        C.max_hit_target = dstName
      end
    end
  elseif dstGUID == me and srcName and (sub:find("_DAMAGE") or sub == "SWING_MISSED") then
    lastAttacker = srcName
  end
end

f:SetScript("OnEvent", function(_, event, ...)
  if not C and event ~= "PLAYER_LOGIN" then return end
  if event == "PLAYER_LOGIN" then
    ensureChar()
    session = { start = now(), kills = 0, xp = 0, dist = 0, gold = 0, dmg = 0, deaths = 0, quests = 0,
                level_start = UnitLevel("player") }
    local z = GetRealZoneText()
    if z and z ~= "" then C.zones[z] = true end
    -- fortsett fra sist lagrede spilletid til WoW sender et nøyaktig tall
    playedBase, playedLevelBase, playedAt = C.played or 0, C.played_level or 0, GetTime()
  elseif event == "TIME_PLAYED_MSG" then
    local total, level = ...
    playedBase, playedLevelBase, playedAt = total, level, GetTime()
    C.played, C.played_level = total, level
  elseif event == "PLAYER_LEVEL_UP" then
    local newLevel = ...
    local total, lvlTime = playedNow()
    C.level_time[newLevel - 1] = lvlTime                 -- så lenge du var på forrige level
    C.levels[newLevel] = { reached = now(), played = total }
    playedBase, playedLevelBase, playedAt = total, 0, GetTime()
    C.level = newLevel
  elseif event == "PLAYER_DEAD" then
    C.deaths = C.deaths + 1
    if session then session.deaths = session.deaths + 1 end
    bump(C.killers, lastAttacker or "Ukjent")
  elseif event == "COMBAT_LOG_EVENT_UNFILTERED" then
    onCombatLog()
  elseif event == "PLAYER_MONEY" then
    local m = GetMoney()
    local d = m - (C.money or m)
    if d > 0 then C.gold_in = C.gold_in + d; if session then session.gold = session.gold + d end
    elseif d < 0 then C.gold_out = C.gold_out - d end
    C.money = m
  elseif event == "QUEST_TURNED_IN" then
    C.quests = C.quests + 1
    if session then session.quests = session.quests + 1 end
  elseif event == "PLAYER_XP_UPDATE" then
    local xp, max = UnitXP("player"), UnitXPMax("player")
    local d
    if xp >= (C.xp_now or 0) then d = xp - (C.xp_now or 0) else d = (C.xp_max or 0) - (C.xp_now or 0) + xp end
    if d > 0 then C.xp = C.xp + d; if session then session.xp = session.xp + d end end
    C.xp_now, C.xp_max = xp, max
  elseif event == "ZONE_CHANGED_NEW_AREA" then
    local z = GetRealZoneText()
    if z and z ~= "" then C.zones[z] = true end
  elseif event == "PLAYER_REGEN_DISABLED" then
    combatStart = GetTime()
  elseif event == "PLAYER_REGEN_ENABLED" then
    if combatStart then C.combat_time = C.combat_time + (GetTime() - combatStart); combatStart = nil end
  elseif event == "PLAYER_LOGOUT" then
    save()
  end
end)

for _, e in ipairs({ "PLAYER_LOGIN", "TIME_PLAYED_MSG", "PLAYER_LEVEL_UP", "PLAYER_DEAD", "COMBAT_LOG_EVENT_UNFILTERED",
                     "PLAYER_MONEY", "QUEST_TURNED_IN", "PLAYER_XP_UPDATE", "ZONE_CHANGED_NEW_AREA",
                     "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED", "PLAYER_LOGOUT" }) do
  pcall(f.RegisterEvent, f, e)
end

-- /ks – vis statistikken i chatten
local function fmtTime(s)
  s = math.floor(s or 0)
  local d, h, m = math.floor(s / 86400), math.floor(s % 86400 / 3600), math.floor(s % 3600 / 60)
  if d > 0 then return string.format("%dd %dt %dm", d, h, m) end
  return string.format("%dt %dm", h, m)
end
SLASH_KONTROLLSENTER1 = "/ks"
SlashCmdList.KONTROLLSENTER = function()
  if not C then return end
  local total, lvl = playedNow()
  local km = 0
  for _, v in pairs(C.dist) do km = km + v end
  km = km * 0.9144 / 1000
  print(string.format("|cff3584e4Kontrollsenter|r %s (%d): spilt %s, på denne leveln %s", C.name, UnitLevel("player"),
    fmtTime(total), fmtTime(lvl)))
  print(string.format("  %.1f km tilbakelagt · %d drept · %d dødsfall · %d quests · %d hopp",
    km, C.kills, C.deaths, C.quests, C.jumps))
end
