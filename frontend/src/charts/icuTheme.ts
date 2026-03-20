type AnyObj = Record<string, any>

function merge(base: AnyObj, extra: AnyObj = {}) {
  return { ...base, ...extra }
}

export function icuTooltip(extra: AnyObj = {}) {
  const base = {
    backgroundColor: 'rgba(4,14,24,.97)',
    borderColor: 'rgba(88,225,255,.2)',
    borderWidth: 1,
    padding: [10, 12],
    textStyle: { color: '#e8fbff', fontSize: 11, lineHeight: 18 },
    extraCssText: 'box-shadow: 0 14px 30px rgba(0,0,0,.34); border-radius: 12px; backdrop-filter: blur(10px);',
    axisPointer: {
      lineStyle: { color: 'rgba(110, 231, 249, 0.22)' },
      crossStyle: { color: 'rgba(110, 231, 249, 0.22)' },
      shadowStyle: { color: 'rgba(56, 189, 248, 0.08)' },
      label: {
        backgroundColor: 'rgba(8, 31, 47, 0.96)',
        color: '#dffbff',
      },
    },
  }
  return {
    ...base,
    ...extra,
    textStyle: merge(base.textStyle, extra.textStyle),
    axisPointer: merge(base.axisPointer, extra.axisPointer),
  }
}

export function icuLegend(extra: AnyObj = {}) {
  const base = {
    top: 0,
    icon: 'roundRect',
    itemWidth: 10,
    itemHeight: 10,
    itemGap: 14,
    textStyle: { color: '#9edff0', fontSize: 10, padding: [0, 0, 0, 4] },
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
    axisLine: { lineStyle: { color: 'rgba(79,182,219,.18)' } },
    axisLabel: { color: '#86d3e8', fontSize: 10, margin: 10 },
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
    axisLine: { show: false, lineStyle: { color: 'rgba(79,182,219,.18)' } },
    axisLabel: { color: '#86d3e8', fontSize: 10 },
    splitLine: { lineStyle: { color: 'rgba(61,118,145,.14)', type: 'dashed' } },
  }
  return {
    ...base,
    ...extra,
    axisLine: merge(base.axisLine, extra.axisLine),
    axisLabel: merge(base.axisLabel, extra.axisLabel),
    splitLine: merge(base.splitLine, extra.splitLine),
  }
}
