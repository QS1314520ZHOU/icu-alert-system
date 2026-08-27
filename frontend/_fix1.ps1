# === PatientDetail.vue: add area nav + setArea ===
$path = 'src/views/PatientDetail.vue'
$c = [System.Collections.ArrayList]@(Get-Content $path)

# 1) Add area nav buttons after density toggle (after line 36 which is </section>)
$areaNav = @(
'    <nav class="pd-area-nav">',
'      <button :class="[\'pd-area-btn\', { \'is-active\': activeArea === \'overview\' }]" @click="setArea(\'overview\')">&#9673; 总览</button>',
'      <button :class="[\'pd-area-btn\', { \'is-active\': activeArea === \'monitoring\' }]" @click="setArea(\'monitoring\')">&#9678; 监护</button>',
'      <button :class="[\'pd-area-btn\', { \'is-active\': activeArea === \'treatment\' }]" @click="setArea(\'treatment\')">&#9764; 治疗与护理</button>',
'      <button :class="[\'pd-area-btn\', { \'is-active\': activeArea === \'decision\' }]" @click="setArea(\'decision\')">&#9888; 预警与决策</button>',
'      <button :class="[\'pd-area-btn\', { \'is-active\': activeArea === \'documents\' }]" @click="setArea(\'documents\')">&#128221; 文书与AI</button>',
'    </nav>',
'',
)
# Insert after line index 36 (0-based)
$idx = 36
$c.InsertRange($idx + 1, $areaNav)

# 2) Add activeArea + setArea after detailTabGroup ref (line 886 originally, but we inserted 8 lines so offset +8)
# Find the line with "const detailTabGroup = ref"
$insertIdx = -1
for ($i = 0; $i -lt $c.Count; $i++) {
  if ($c[$i] -match "const detailTabGroup = ref") { $insertIdx = $i; break }
}
if ($insertIdx -ge 0) {
  $areaCode = @(
    "type DetailAreaKey = `"overview`" | `"monitoring`" | `"treatment`" | `"decision`" | `"documents`"",
    "const activeArea = ref<DetailAreaKey>((route.query.area as DetailAreaKey) || 'overview')",
    "const areaTabGroupMap: Record<DetailAreaKey, { group: DetailTabGroup; tab: DetailTabKey }> = @{",
    "  overview = @{ group = 'focus'; tab = 'alerts' }",
    "  monitoring = @{ group = 'monitor'; tab = 'trend' }",
    "  treatment = @{ group = 'therapy'; tab = 'drugs' }",
    "  decision = @{ group = 'focus'; tab = 'alerts' }",
    "  documents = @{ group = 'ai'; tab = 'documents' }",
    "}",
  )
  # Use proper TS object literal syntax
  $areaCodeTs = @(
    "type DetailAreaKey = `"overview`" | `"monitoring`" | `"treatment`" | `"decision`" | `"documents`"",
    "const activeArea = ref<DetailAreaKey>((route.query.area as DetailAreaKey) || 'overview')",
    "const areaTabGroupMap: Record<DetailAreaKey, { group: DetailTabGroup; tab: DetailTabKey }> = {",
    "  overview: { group: 'focus', tab: 'alerts' },",
    "  monitoring: { group: 'monitor', tab: 'trend' },",
    "  treatment: { group: 'therapy', tab: 'drugs' },",
    "  decision: { group: 'focus', tab: 'alerts' },",
    "  documents: { group: 'ai', tab: 'documents' },",
    "}",
    "function setArea(area: DetailAreaKey) {",
    "  activeArea.value = area",
    "  const { group, tab } = areaTabGroupMap[area]",
    "  switchTabGroup(group)",
    "  activeTab.value = tab",
    "  router.replace({ query: { ...route.query, area, tab } })",
    "}",
  )
  $c.InsertRange($insertIdx + 1, $areaCodeTs)
}

Set-Content $path $c -Encoding UTF8
Write-Host "PatientDetail.vue patched"
