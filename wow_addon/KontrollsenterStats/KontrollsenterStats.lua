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

-- Nyere WoW gir «secret values» (skjulte tall/tekster) fra enkelte API-er i kamp og instanser.
-- Addons kan ikke sammenligne, regne med eller bruke dem som tabellnøkler – da kommer Lua-feil.
local function secret(v) return issecretvalue ~= nil and issecretvalue(v) == true end
local function plainName(v)
  if v == nil or secret(v) or type(v) ~= "string" or v == "" then return nil end
  return v
end

local function bump(t, key, n)
  key = plainName(key)
  if not key then return end
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
  local guid = UnitGUID and UnitGUID("player") or nil
  local old = db.chars[key]
  if old then
    -- en ny karakter med samme navn som en slettet: start på nytt i stedet for å arve den gamles tall
    local cls = select(2, UnitClass("player"))
    if (old.guid and guid and old.guid ~= guid)
        or (not old.guid and ((old.class and old.class ~= cls) or (old.race and old.race ~= UnitRace("player"))
                              or (old.level or 0) > (UnitLevel("player") or 0))) then
      old = nil
    end
  end
  db.chars[key] = old or { first_seen = now() }
  C = db.chars[key]
  C.guid = guid or C.guid
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

-- distanse: fart (yards/s) × tid, sortert etter hvordan du beveger deg.
-- Når WoW skjuler farten (secret value), brukes hvor langt posisjonen har flyttet seg i stedet.
-- C.dist_src teller sekunder per kilde (speed/pos/none), så Kontrollsenter kan se hva som virker.
local acc = 0
local lastX, lastY, lastInst
local function flag(fn)                       -- true/false fra IsFlying o.l., aldri en skjult verdi
  if not fn then return false end
  local v = fn("player")
  if secret(v) then return false end
  return v and true or false
end
local function position()
  if not UnitPosition then return nil end
  local y, x, _, inst = UnitPosition("player")
  if secret(x) or secret(y) or secret(inst) or type(x) ~= "number" or type(y) ~= "number" then return nil end
  return x, y, inst
end
f:SetScript("OnUpdate", function(_, elapsed)
  acc = acc + elapsed
  if acc < 0.25 or not C then return end
  local dt = acc; acc = 0
  local x, y, inst = position()
  local speed = GetUnitSpeed and GetUnitSpeed("player") or 0
  local yards, src
  if not secret(speed) and type(speed) == "number" then
    yards, src = speed, "speed"
    yards = yards * dt
  elseif x and lastX and inst == lastInst then
    local d = math.sqrt((x - lastX) ^ 2 + (y - lastY) ^ 2)
    if d < 120 * dt then yards, src = d, "pos" else yards, src = 0, "pos" end   -- hopp = teleport/lasting
  else
    yards, src = 0, "none"
  end
  lastX, lastY, lastInst = x, y, inst
  C.dist_src = C.dist_src or {}
  C.dist_src[src] = (C.dist_src[src] or 0) + dt
  if yards <= 0.01 then return end
  local kind = "walk"
  if flag(UnitOnTaxi) then kind = "taxi"
  elseif flag(IsFlying) then kind = "fly"
  elseif flag(IsSwimming) then kind = "swim"
  elseif flag(IsMounted) then kind = "mount" end
  C.dist[kind] = (C.dist[kind] or 0) + yards
  if session then session.dist = session.dist + yards end
end)

if hooksecurefunc and JumpOrAscendStart then
  hooksecurefunc("JumpOrAscendStart", function()
    if C and not flag(UnitOnTaxi) then C.jumps = C.jumps + 1 end
  end)
end

-- Kills: «X dies, you gain N experience» (kamploggen er låst for addons i nyere WoW, så den brukes ikke)
local xpPattern
do
  local fmt = COMBATLOG_XPGAIN_FIRSTPERSON or "%s dies, you gain %d experience."
  local prefix = fmt:match("^(.-)%%d") or fmt
  prefix = prefix:gsub("([%(%)%.%+%-%*%?%[%]%^%$])", "%%%1"):gsub("%%s", "(.-)")
  xpPattern = "^" .. prefix
end

f:SetScript("OnEvent", function(_, event, ...)
  if not C and event ~= "PLAYER_LOGIN" and event ~= "ADDON_ACTION_FORBIDDEN" and event ~= "ADDON_ACTION_BLOCKED" then
    return
  end
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
    local killer = (UnitExists and UnitExists("target") and UnitCanAttack and UnitCanAttack("player", "target"))
      and plainName(UnitName("target")) or lastAttacker
    bump(C.killers, killer or "Ukjent")
  elseif event == "PLAYER_TARGET_CHANGED" then
    if UnitExists and UnitExists("target") and UnitCanAttack and UnitCanAttack("player", "target") then
      lastAttacker = plainName(UnitName("target")) or lastAttacker
    end
  elseif event == "CHAT_MSG_COMBAT_XP_GAIN" then
    local msg = ...
    local victim = plainName(msg) and msg:match(xpPattern)
    if victim and victim ~= "" then
      C.kills = C.kills + 1
      bump(C.kills_by, victim)
      if session then session.kills = session.kills + 1 end
    end
  elseif event == "ADDON_ACTION_FORBIDDEN" or event == "ADDON_ACTION_BLOCKED" then
    local who, fn = ...
    if who == ADDON then
      KontrollsenterStatsDB = KontrollsenterStatsDB or { version = 1, chars = {} }
      KontrollsenterStatsDB.blocked = { event = event, func = tostring(fn), at = now() }
    end
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

-- bare vanlige hendelser – ingen kamplogg, ingen låste funksjoner
for _, e in ipairs({ "ADDON_ACTION_FORBIDDEN", "ADDON_ACTION_BLOCKED", "PLAYER_LOGIN", "TIME_PLAYED_MSG",
                     "PLAYER_LEVEL_UP", "PLAYER_DEAD", "PLAYER_TARGET_CHANGED", "CHAT_MSG_COMBAT_XP_GAIN",
                     "PLAYER_MONEY", "QUEST_TURNED_IN", "PLAYER_XP_UPDATE", "ZONE_CHANGED_NEW_AREA",
                     "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED", "PLAYER_LOGOUT" }) do
  f:RegisterEvent(e)
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
  if KontrollsenterStatsDB.blocked then
    print("|cffff5555Kontrollsenter: WoW blokkerte " .. KontrollsenterStatsDB.blocked.func .. "|r")
  end
  local total, lvl = playedNow()
  local km = 0
  for _, v in pairs(C.dist) do km = km + v end
  km = km * 0.9144 / 1000
  print(string.format("|cff3584e4Kontrollsenter|r %s (%d): spilt %s, på denne leveln %s", C.name, UnitLevel("player"),
    fmtTime(total), fmtTime(lvl)))
  print(string.format("  %.1f km tilbakelagt · %d drept · %d dødsfall · %d quests · %d hopp",
    km, C.kills, C.deaths, C.quests, C.jumps))
end
