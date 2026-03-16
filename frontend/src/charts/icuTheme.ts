type AnyObj = Record<string, any>

function merge(base: AnyObj, extra: AnyObj = {}) {
  return { ...base, ...extra }
}

export function icuTooltip(extra: AnyObj = {}) {
  const base = {
    backgroundColor: 'rgba(5,17,29,.96)',
    borderColor: 'rgba(88,225,255,.24)',
    borderWidth: 1,
    textStyle: { color: '#dffbff', fontSize: 11 },
    extraCssText: 'box-shadow: 0 12px 28px rgba(0,0,0,.28); border-radius: 10px;',
  }
  return {
    ...base,
    ...extra,
    textStyle: merge(base.textStyle, extra.textStyle),
  }
}

export function icuLegend(extra: AnyObj = {}) {
  const base = {
    top: 0,
    itemWidth: 10,
    itemHeight: 10,
    itemGap: 12,
    textStyle: { color: '#8fd4e6', fontSize: 10 },
  }
  return {
    ...base,
    ...extra,
    textStyle: merge(base.textStyle, extra.textStyle),
  }
}

export function icuGrid(extra: AnyObj = {}) {
  return {
    containLabel: false,
    ...extra,
  }
}

export function icuCategoryAxis(data: any[], extra: AnyObj = {}) {
  const base = {
    type: 'category',
    data,
    axisTick: { show: false },
    axisLine: { lineStyle: { color: 'rgba(79,182,219,.22)' } },
    axisLabel: { color: '#7ecce1', fontSize: 10, margin: 10 },
  }
  return {
    ...base,
    ...extra,
    axisTick: merge(base.axisTick, extra.axisTick),
    axisLine: merge(base.axisLine, extra.axisLine),
    axisLabel: merge(base.axisLabel, extra.axisLabel),
  }
}

export function icuValueAxis(extra: AnyObj = {}) {
  const base = {
    type: 'value',
    axisLine: { show: false, lineStyle: { color: 'rgba(79,182,219,.22)' } },
    axisLabel: { color: '#7ecce1', fontSize: 10 },
    splitLine: { lineStyle: { color: 'rgba(61,118,145,.16)' } },
  }
  return {
    ...base,
    ...extra,
    axisLine: merge(base.axisLine, extra.axisLine),
    axisLabel: merge(base.axisLabel, extra.axisLabel),
    splitLine: merge(base.splitLine, extra.splitLine),
  }
}
