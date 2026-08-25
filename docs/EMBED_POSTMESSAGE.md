# SmartCare embed.html 嵌入地址与 postMessage 通信说明

## 一、整体架构

```
宿主 HIS/EMR (Angular)
|
+-- 外层 iframe  <-- 宿主填 src，指向 embed.html
|   +-- 内层 iframe  <-- embed.html 自动设置 frame.src，加载 SmartCare Vue SPA
```

## 二、通信流程

1. 宿主打开 embed.html?page=xxx
2. embed.html 向宿主发 SmartCareReady
3. 宿主收到后，postMessage SmartCare 载荷（account + patient + token）
4. embed.html 解析载荷，翻译患者 ID，渲染内层页面

```
宿主                                embed.html
  |                                    |
  |       iframe 加载完成              |
  |<-----------------------------------|
  |                                    |
  |  { type: SmartCareReady }          |
  |<-----------------------------------|  (每 400ms 重发，最多 20 次)
  |                                    |
  |  { type: SmartCare, ... }          |
  |----------------------------------->|
  |                                    |
  |  握手完成，开始渲染页面             |
```

## 三、外层地址（宿主填的 iframe src）

格式: http://<SmartCare服务器>/embed.html?page=<别名>

## 四、内层地址（embed.html 自动生成）

格式: /<路由路径>?user_id=xxx&userName=xxx&role=xxx&dept=xxx&dept_code=xxx

宿主不需要手动拼内层地址，embed.html 的 buildUrl() 自动完成。

## 五、各模块地址明细

### 不需要患者的模块（直接填外层地址即可，无需 postMessage）

| 模块 | page 值 | 外层地址 | 内层路由 |
|------|---------|---------|---------|
| 患者列表 | patients | .../embed.html?page=patients | /patients |
| 大屏看板 | bigscreen | .../embed.html?page=bigscreen | /bigscreen |
| 临床工作流 | clinical | .../embed.html?page=clinical | /clinical-workflow |
| 查房记录 | rounding | .../embed.html?page=rounding | /rounding-sheet |
| 呼吸治疗 | respiratory | .../embed.html?page=respiratory | /respiratory-dashboard |
| 营养支持 | nutrition | .../embed.html?page=nutrition | /nutrition-support |
| 数据分析 | analytics | .../embed.html?page=analytics | /analytics |
| AI 会诊 | ai-consult | .../embed.html?page=ai-consult | /ai-consult |
| MDT 会诊 | mdt | .../embed.html?page=mdt | /mdt |
| 交接班 | handover | .../embed.html?page=handover | /handover |
| 科研工作台 | research | .../embed.html?page=research | /research-workbench |
| 学术研究 | academic | .../embed.html?page=academic | /academic-research |
| 临床试验 | trials | .../embed.html?page=trials | /clinical-trials |
| 医生工作台 | doctor-home | .../embed.html?page=doctor-home | /doctor-home |
| 护士工作台 | nurse-home | .../embed.html?page=nurse-home | /nurse-home |
| 护士长工作台 | head-nurse-home | .../embed.html?page=head-nurse-home | /head-nurse-home |
| 主任工作台 | director-home | .../embed.html?page=director-home | /director-home |
| 运行时配置 | admin-config | .../embed.html?page=admin-config | /admin/runtime-config |
| 扫描器健康 | scanner-health | .../embed.html?page=scanner-health | /admin/scanner-health |
| AI 运维 | ai-ops | .../embed.html?page=ai-ops | /ai-ops |
| 科研导出 | research-export | .../embed.html?page=research-export | /research-export |
| 语音审核 | voice-review | .../embed.html?page=voice-review | /admin/voice-correction-review |
| 移动端 | mobile | .../embed.html?page=mobile | /m |

### 需要患者的模块（必须 postMessage 传入 patient）

| 模块 | page 值 | 外层地址 | 内层路由 |
|------|---------|---------|---------|
| 患者详情 | patient | .../embed.html?page=patient | /patient/<MongoID> |
| 床旁视图 | bedside | .../embed.html?page=bedside | /bedside/<MongoID> |

## 六、postMessage 协议

### 宿主发送的消息格式

```javascript
iframeWindow.postMessage({
  type: 'SmartCare',
  account: this.system.currentAccount,   // 当前登录账号
  patient: this.system.currentPatient,   // 当前患者
  token: this.system.token               // 认证令牌
}, 'http://<SmartCare服务器>');
```

### account 对象 -- 身份字段映射

embed.html 会从 account 中按以下优先级读取:

| 输出字段 | 读取优先级（从左到右） | 说明 |
|---------|----------------------|------|
| user_id | user_id, userId, id, empNo, code, staffCode, empCode, loginName, accountName | 工号 |
| userName | userName, username, name, realName, staffName, staffCode, empCode, actor, loginName, trueName, displayName | 姓名（必填） |
| role | role, roleCode, roleName, userRole | 角色 |
| dept | patient.dept, account.dept, deptName, department, departmentName | 科室名称 |
| dept_code | patient.deptCode, patient.deptCode2, patient.dept_code, patient.departmentCode, account.deptCode, account.dept_code, account.departmentCode | 科室代码（必填） |

### patient 对象 -- 关键字段

| 字段 | 说明 | 示例 |
|------|------|------|
| name | 患者姓名 | 卢旭莉 |
| gender | 性别英文 | Female / Male |
| genderStr | 性别中文 | 女 / 男 |
| dept | 科室名称 | ICU |
| deptCode | 科室代码（必填） | 112 |
| deptCode2 | 科室代码备用 | 112 |
| showBed | 床号 | 5 |
| hisBed | HIS 床号 | 5 |
| mrn | 住院号 | 14904268 |
| hisPid | HIS 患者 ID | 4590295 |
| hospitalTime | 住院次数 | 1 |

### 完整消息示例

```json
{
  "type": "SmartCare",
  "account": {
    "empNo": "emp001",
    "name": "张医生",
    "role": "医生",
    "dept": "ICU",
    "deptCode": "112"
  },
  "patient": {
    "name": "卢旭莉",
    "gender": "Female",
    "genderStr": "女",
    "dept": "ICU",
    "deptCode": "112",
    "deptCode2": "112",
    "showBed": "5",
    "hisBed": "5",
    "mrn": "14904268",
    "hisPid": "4590295",
    "hospitalTime": "1"
  },
  "token": "..."
}
```

## 七、宿主 Angular 参考代码

```typescript
export class IframeViewComponent implements OnInit, OnDestroy {
  private readonly printOrigin = 'http://192.168.5.154:18088';

  private onHostMessage = (e: MessageEvent) => {
    if (e.origin !== this.printOrigin) return;

    if (e?.data?.type === 'SmartCareReady' && e.source) {
      const patient = this.system.currentPatient;
      const param = {
        type: 'SmartCare',
        account: this.system.currentAccount,
        patient,
        token: this.system.token,
      };
      (e.source as Window).postMessage(param, this.printOrigin);
    }
  };

  ngOnInit(): void {
    window.addEventListener('message', this.onHostMessage);
  }

  ngOnDestroy(): void {
    window.removeEventListener('message', this.onHostMessage);
  }
}
```

## 八、三个常见问题排查

### 1. 左侧菜单栏仍显示

原因: hideChrome CSS 之前只隐藏了 header，没有隐藏侧边栏。
修复: 已添加 .side-nav{display:none!important} 和 .shell-main{flex:1 1 100%!important}。

### 2. 操作人显示"请输入工号/姓名"

原因: 宿主 account 对象中没有 userName 字段（或字段名不匹配）。
排查: 打开 F12 Console，看 [embed] account: 日志，确认 account 对象有哪些字段。
修复: embed.html 现已支持 12 种常见字段名。
如果仍不显示: 宿主 account 中需要用以上任一字段名传入用户姓名。

### 3. 患者列表拉了全院病人（deptCode 没传）

原因: postMessage 的 patient 或 account 中没有 deptCode 字段。
排查: 打开 F12 Console，看 [embed] patient: 日志，确认 patient.deptCode 是否有值。
修复: 确保 patient.deptCode 或 account.deptCode 有值。
日志警告: 如果 dept_code 为空，Console 会输出 [embed] 警告：未收到 dept_code。

## 九、调试方法

1. 打开宿主系统，按 F12 进入 Console
2. 筛选 [embed] 前缀
3. 应依次看到:
   - [embed] account: {...} -- 宿主账号信息
   - [embed] patient: {...} -- 患者信息（含 deptCode）
   - [embed] identity: {...} -- embed 解析后的身份信息
4. 如果 identity.dept_code 为空 -> 宿主没传 deptCode
5. 如果 identity.userName 为空 -> 宿主没传姓名字段

## 十、安全要求

1. 正式环境不要用 * 作为 targetOrigin
2. 宿主收到消息时校验 e.origin
3. embed.html 的 CONFIG.allowedHostOrigins 必须包含宿主 origin
4. 不在控制台打印完整 token
5. patient 只用于当前患者查询，不应缓存到 localStorage
6. 切换患者后应重新 postMessage 最新 patient
