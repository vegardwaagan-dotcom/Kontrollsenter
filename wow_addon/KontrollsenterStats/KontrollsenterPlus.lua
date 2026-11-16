-- Kontrollsenter Stats – ekstra: uthvilt XP, yrker, questlogg, gull over tid, raid-låser, utstyr og bagger/bank.
-- Bare lesing med vanlige addon-funksjoner (det samme som Bagnon, Questie o.l. bruker) – ingen automatisering.
-- Slås av og på i Kontrollsenter, som skriver KontrollsenterConfig.lua. Endringer gjelder etter /reload.
-- Alt lagres når du logger ut eller skriver /reload (da skriver WoW SavedVariables til disk).

local cfg = KS_CONFIG or {}
local function on(k) return cfg.on ~= false and cfg[k] ~= false end

local function me()
  local db = KontrollsenterStatsDB
  if not db or not db.chars or not UnitName("player") then return nil end
  return db.chars[GetRealmName() .. "-" .. UnitName("player")]
end

local function safe(fn, C) pcall(fn, C) end

-- ---------- uthvilt XP og hvor du er (oversikt over karakterene) ----------
local function scanAlt(C)
  C.rested = GetXPExhaustion and (GetXPExhaustion() or 0) or 0
  C.resting = IsResting and IsResting() and true or false
  C.xp_now, C.xp_max = UnitXP("player"), UnitXPMax("player")
  C.zone = GetRealZoneText and GetRealZoneText() or C.zone
  C.subzone = GetSubZoneText and GetSubZoneText() or nil
end

-- ---------- yrker (og når hvert femte nivå ble nådd) ----------
local function scanProfs(C)
  if not GetNumSkillLines or not GetSkillLineInfo then return end
  local out, header = {}, nil
  for i = 1, GetNumSkillLines() do
    local name, isHeader, _, rank, _, _, maxRank = GetSkillLineInfo(i)
    if isHeader then
      header = name
    elseif name and maxRank and maxRank > 1 then
      out[name] = { rank = rank or 0, max = maxRank, cat = header }
    end
  end
  C.profs = out
  C.prof_hist = C.prof_hist or {}
  for n, p in pairs(out) do
    if p.rank and p.rank % 5 == 0 then
      local h = C.prof_hist[n] or {}
      if not h[p.rank] then h[p.rank] = time() end
      C.prof_hist[n] = h
    end
  end
end

-- ---------- questloggen ----------
local function scanQuests(C)
  if not GetNumQuestLogEntries or not GetQuestLogTitle then return end
  local q, header = {}, nil
  for i = 1, GetNumQuestLogEntries() do
    local title, level, _, isHeader, _, isComplete = GetQuestLogTitle(i)
    if isHeader then
      header = title
    elseif title then
      local obj = {}
      if GetNumQuestLeaderBoards and GetQuestLogLeaderBoard then
        for j = 1, (GetNumQuestLeaderBoards(i) or 0) do
          local text, _, done = GetQuestLogLeaderBoard(j, i)
          if text then obj[#obj + 1] = (done and "+ " or "- ") .. text end
        end
      end
      q[#q + 1] = { title = title, level = level, zone = header,
                    done = (isComplete == 1 or isComplete == true), obj = obj }
    end
  end
  C.quest_log = q
end

-- ---------- gull over tid ----------
local function scanGold(C)
  C.gold_hist = C.gold_hist or {}
  local h, m = C.gold_hist, GetMoney()
  local last = h[#h]
  if not last or last.g ~= m then
    h[#h + 1] = { t = time(), g = m }
    while #h > 200 do table.remove(h, 1) end
  end
end

-- ---------- raid- og dungeon-låser ----------
local function scanLocks(C)
  if not GetNumSavedInstances or not GetSavedInstanceInfo then return end
  local out = {}
  for i = 1, GetNumSavedInstances() do
    local name, _, reset, _, locked = GetSavedInstanceInfo(i)
    if name and reset and reset > 0 and locked ~= false then
      out[#out + 1] = { name = name, reset_at = time() + reset }
    end
  end
  C.locks = out
end

-- ---------- utstyr (reparasjon) ----------
local function scanDurability(C)
  if not GetInventoryItemDurability then return end
  local lo, sum, n = 1, 0, 0
  for slot = 1, 18 do
    local cur, max = GetInventoryItemDurability(slot)
    if cur and max and max > 0 then
      local r = cur / max
      if r < lo then lo = r end
      sum, n = sum + r, n + 1
    end
  end
  C.durability = n > 0 and { min = math.floor(lo * 100 + 0.5), avg = math.floor(sum / n * 100 + 0.5), t = time() } or nil
end

-- ---------- bagger og bank ----------
local CC = C_Container
local function numSlots(b)
  if CC and CC.GetContainerNumSlots then return CC.GetContainerNumSlots(b) or 0 end
  return GetContainerNumSlots and GetContainerNumSlots(b) or 0
end
local function itemAt(b, s)
  if CC and CC.GetContainerItemInfo then
    local i = CC.GetContainerItemInfo(b, s)
    if i then return i.hyperlink, i.stackCount end
    return nil
  end
  if GetContainerItemInfo then
    local _, count, _, _, _, _, link = GetContainerItemInfo(b, s)
    return link, count
  end
end
local function scanContainers(list)
  local out = {}
  for _, b in ipairs(list) do
    for s = 1, numSlots(b) do
      local link, count = itemAt(b, s)
      local name = type(link) == "string" and link:match("%[(.-)%]")
      if name then out[name] = (out[name] or 0) + (count or 1) end
    end
  end
  return out
end
local BAGS = { 0, 1, 2, 3, 4 }
local function bankList()
  local l = { BANK_CONTAINER or -1 }
  local first = (NUM_BAG_SLOTS or 4) + 1
  for b = first, first + (NUM_BANKBAGSLOTS or 6) - 1 do l[#l + 1] = b end
  return l
end
local function scanBags(C) C.bags = scanContainers(BAGS); C.bags_t = time() end
local function scanBank(C) C.bank = scanContainers(bankList()); C.bank_t = time() end

-- ---------- egenskaper (karakterarket) og talenter ----------
local STAT = { "str", "agi", "sta", "int", "spi" }
local function num(...) local v = ...; return type(v) == "number" and v or nil end
local function scanSheet(C)
  local s = {}
  for i = 1, 5 do
    local _, stat = UnitStat("player", i)
    s[STAT[i]] = stat
  end
  local base, eff = UnitArmor("player"); s.armor = eff or base
  if UnitAttackPower then local b, p, n = UnitAttackPower("player"); if b then s.ap = b + (p or 0) + (n or 0) end end
  if UnitRangedAttackPower then local b, p, n = UnitRangedAttackPower("player"); if b then s.rap = b + (p or 0) + (n or 0) end end
  if GetCritChance then s.crit = num(GetCritChance()) end
  if GetRangedCritChance then s.rcrit = num(GetRangedCritChance()) end
  if GetSpellCritChance then s.scrit = num(GetSpellCritChance(2)) end
  if GetDodgeChance then s.dodge = num(GetDodgeChance()) end
  if GetParryChance then s.parry = num(GetParryChance()) end
  if GetBlockChance then s.block = num(GetBlockChance()) end
  if GetHitModifier then s.hit = num(GetHitModifier()) end
  if GetSpellHitModifier then s.shit = num(GetSpellHitModifier()) end
  if GetSpellBonusDamage then
    local m = 0
    for school = 2, 7 do m = math.max(m, GetSpellBonusDamage(school) or 0) end
    s.sp = m
  end
  if GetSpellBonusHealing then s.heal = num(GetSpellBonusHealing()) end
  if UnitDefense then local b, m = UnitDefense("player"); if b then s.def = b + (m or 0) end end
  s.hp = UnitHealthMax("player")
  s.mana = UnitPowerMax and UnitPowerMax("player", 0) or (UnitManaMax and UnitManaMax("player")) or nil
  s.res = {}
  for i = 2, 6 do local _, total = UnitResistance("player", i); s.res[i] = total or 0 end
  C.sheet, C.sheet_t = s, time()
  -- talenter: navn og poeng per tre (Classic: navn, ikon, poeng – nyere: id, navn, …, poeng)
  local t = {}
  if GetNumTalentTabs and GetTalentTabInfo then
    for i = 1, GetNumTalentTabs() do
      local a, b, c, _, e = GetTalentTabInfo(i)
      if type(a) == "string" then t[i] = { name = a, points = tonumber(c) or 0 }
      else t[i] = { name = b, points = tonumber(e) or 0 } end
    end
  end
  C.talents = t
  local unspent = UnitCharacterPoints and UnitCharacterPoints("player")
  if unspent == nil and GetUnspentTalentPoints then unspent = GetUnspentTalentPoints() end
  C.unspent = tonumber(unspent) or 0
end

-- ---------- chatlogg (for varsel på telefonen ved hvisking) ----------
-- WoW skriver chatten til Logs/WoWChatLog.txt når logging er på (/chatlog). Kontrollsenter leser fila.
local function chatLog()
  local db = KontrollsenterStatsDB
  if not LoggingChat or not db then return end
  if on("chat") then
    if not LoggingChat() then LoggingChat(true); db.ks_chatlog = true end
  elseif db.ks_chatlog then                       -- bare slå av det vi selv slo på
    if LoggingChat() then LoggingChat(false) end
    db.ks_chatlog = nil
  end
end

local function scanAll(C)
  if not C or cfg.on == false then return end
  if on("alts") then safe(scanAlt, C) end
  if on("profs") then safe(scanProfs, C) end
  if on("quests") then safe(scanQuests, C) end
  if on("gold") then safe(scanGold, C) end
  if on("locks") then safe(scanLocks, C) end
  if on("durability") then safe(scanDurability, C) end
  if on("bags") then safe(scanBags, C) end
  if on("sheet") then safe(scanSheet, C) end
end

local bankOpen = false
local f = CreateFrame("Frame")
f:SetScript("OnEvent", function(_, event)
  local C = me()
  if event == "PLAYER_LOGIN" then
    pcall(chatLog)
    if on("locks") and RequestRaidInfo then pcall(RequestRaidInfo) end
    scanAll(C)
  elseif event == "CHARACTER_POINTS_CHANGED" or event == "PLAYER_LEVEL_UP" then
    if C and on("sheet") then safe(scanSheet, C) end
  elseif event == "UPDATE_INSTANCE_INFO" then
    if C and on("locks") then safe(scanLocks, C) end
  elseif event == "BANKFRAME_OPENED" then
    bankOpen = true
    if C and on("bags") then safe(scanBank, C) end
  elseif event == "BANKFRAME_CLOSED" then
    bankOpen = false
  elseif event == "BAG_UPDATE_DELAYED" or event == "PLAYERBANKSLOTS_CHANGED" then
    if C and bankOpen and on("bags") then safe(scanBank, C) end
  elseif event == "PLAYER_LOGOUT" then
    scanAll(C)
  end
end)
for _, e in ipairs({ "PLAYER_LOGIN", "UPDATE_INSTANCE_INFO", "BANKFRAME_OPENED", "BANKFRAME_CLOSED",
                     "BAG_UPDATE_DELAYED", "PLAYERBANKSLOTS_CHANGED", "PLAYER_LOGOUT",
                     "CHARACTER_POINTS_CHANGED", "PLAYER_LEVEL_UP" }) do
  pcall(f.RegisterEvent, f, e)
end
