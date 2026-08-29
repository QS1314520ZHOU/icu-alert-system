/**
 * useClinicalChart — 统一 ECharts Composable
 *
 * 负责 ECharts 实例的完整生命周期管理：
 * - 初始化 / 销毁
 * - option 更新
 * - 主题切换（light/dark）
 * - ResizeObserver 自适应
 * - 页面 visibility 变化处理
 * - 导出 PNG / SVG
 * - 异常捕获
 */

import { ref, watch, onMounted, onBeforeUnmount, nextTick, type Ref, shallowRef } from 'vue'
import * as echarts from 'echarts'
import { getThemeMode, useThemeMode } from './themeMode'

export interface ClinicalChartOptions {
  /** 容器 ref */
  containerRef: Ref<HTMLElement | null>
  /** ECharts option */
  option: Ref<echarts.EChartsOption | null | undefined>
  /** 是否加载中 */
  loading?: Ref<boolean>
  /** 图表高度，默认 300 */
  height?: number
  /** 是否自动 resize，默认 true */
  autoresize?: boolean
  /** 主题覆盖，不传则跟随全局 */
  theme?: 'light' | 'dark' | 'clinical-light' | 'clinical-dark'
}

export function useClinicalChart(opts: ClinicalChartOptions) {
  const { containerRef, option, loading, autoresize = true } = opts

  const chartInstance = shallowRef<echarts.ECharts | null>(null)
  const isReady = ref(false)
  const chartError = ref('')
  let resizeObserver: ResizeObserver | null = null
  let disposed = false

  // ── 主题 ─────────────────────────────────────────

  function resolveTheme(): string {
    if (opts.theme) return opts.theme
    const mode = getThemeMode() || useThemeMode().value || 'light'
    return mode === 'dark' ? 'clinical-dark' : 'clinical-light'
  }

  // ── 初始化 ───────────────────────────────────────

  function init() {
    const el = containerRef.value
    if (!el || disposed) return

    try {
      // 如果已有实例先销毁
      if (chartInstance.value) {
        chartInstance.value.dispose()
      }

      const theme = resolveTheme()
      chartInstance.value = echarts.init(el, theme, { renderer: 'canvas' })
      isReady.value = true
      chartError.value = ''

      // 设置初始 option
      if (option.value) {
        chartInstance.value.setOption(option.value, true)
      }

      // loading 状态
      if (loading?.value) {
        chartInstance.value.showLoading('default', {
          text: '',
          color: '#2563EB',
          maskColor: 'rgba(255,255,255,0.8)',
          spinnerRadius: 12,
          lineWidth: 2,
        })
      }
    } catch (err: any) {
      chartError.value = err?.message || '图表初始化失败'
      console.warn('[ClinicalChart] init error:', err)
    }
  }

  // ── 更新 option ──────────────────────────────────

  function updateOption(newOption: echarts.EChartsOption, notMerge = false) {
    if (!chartInstance.value || disposed) return
    try {
      chartInstance.value.setOption(newOption, { notMerge })
    } catch (err: any) {
      console.warn('[ClinicalChart] setOption error:', err)
    }
  }

  // ── Loading 状态 ─────────────────────────────────

  function showLoading() {
    chartInstance.value?.showLoading('default', {
      text: '',
      color: '#2563EB',
      maskColor: 'rgba(255,255,255,0.8)',
      spinnerRadius: 12,
      lineWidth: 2,
    })
  }

  function hideLoading() {
    chartInstance.value?.hideLoading()
  }

  // ── Resize ───────────────────────────────────────

  function resize() {
    if (!chartInstance.value || disposed) return
    try {
      chartInstance.value.resize({ animation: { duration: 200 } })
    } catch {}
  }

  // ── 导出 ─────────────────────────────────────────

  function exportPNG(pixelRatio = 2): string | null {
    if (!chartInstance.value) return null
    try {
      return chartInstance.value.getDataURL({ type: 'png', pixelRatio, backgroundColor: '#fff' })
    } catch { return null }
  }

  function exportSVG(): string | null {
    if (!chartInstance.value) return null
    try {
      return chartInstance.value.getDataURL({ type: 'svg' })
    } catch { return null }
  }

  // ── 原始数据 ─────────────────────────────────────

  function getOption(): echarts.EChartsOption | null {
    if (!chartInstance.value) return null
    try {
      return chartInstance.value.getOption() as echarts.EChartsOption
    } catch { return null }
  }

  // ── 销毁 ─────────────────────────────────────────

  function dispose() {
    disposed = true
    if (resizeObserver) {
      resizeObserver.disconnect()
      resizeObserver = null
    }
    if (chartInstance.value) {
      chartInstance.value.dispose()
      chartInstance.value = null
    }
    isReady.value = false
  }

  // ── 生命周期 ─────────────────────────────────────

  onMounted(() => {
    nextTick(() => {
      init()

      // ResizeObserver
      if (autoresize && containerRef.value) {
        resizeObserver = new ResizeObserver(() => {
          if (!disposed) resize()
        })
        resizeObserver.observe(containerRef.value)
      }
    })
  })

  onBeforeUnmount(() => {
    dispose()
  })

  // option 变化时更新
  watch(option, (newOpt) => {
    if (newOpt && chartInstance.value && !disposed) {
      updateOption(newOpt)
    }
  }, { deep: false })

  // loading 变化
  if (loading) {
    watch(loading, (isLoading) => {
      if (disposed) return
      if (isLoading) showLoading()
      else hideLoading()
    })
  }

  // 页面 visibility 变化时 resize
  function handleVisibility() {
    if (!document.hidden && !disposed) {
      setTimeout(resize, 100)
    }
  }

  onMounted(() => {
    document.addEventListener('visibilitychange', handleVisibility)
  })

  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', handleVisibility)
  })

  return {
    chartInstance,
    isReady,
    chartError,
    init,
    updateOption,
    showLoading,
    hideLoading,
    resize,
    exportPNG,
    exportSVG,
    getOption,
    dispose,
  }
}
