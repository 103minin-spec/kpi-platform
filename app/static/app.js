const { createApp, ref, reactive, computed, onMounted, nextTick } = Vue;

const app = createApp({
  setup() {
    // Navigation & General
    const currentTab = ref('dashboard');
    const allUsers = ref([]);
    const selectedUserId = ref(1);
    const currentUser = ref({ id: 1, full_name: 'Загрузка...', role: 'ADMIN' });
    const authToken = ref(localStorage.getItem('kpi_token') || '');
    const bitrixStatus = ref({ mock_mode: true, is_configured: false });
    const apiOnline = ref(true);
    const apiError = ref('');

    // Periods & Results
    const periods = ref([]);
    const selectedPeriodId = ref(null);
    const currentResults = ref([]);
    const calculating = ref(false);
    const selectedResultModal = ref(null);
    const showNewPeriodModal = ref(false);
    const periodFormError = ref('');
    const creating = ref(false);
    const notice = ref(null);
    let noticeTimer = null;
    const newPeriodForm = reactive({
      name: '',
      start_date: '2026-11-01',
      end_date: '2026-11-30'
    });

    // Formula Builder & Sandbox
    const variablesCatalog = ref([]);
    const allPositions = ref([]);
    const selectedPositionId = ref(null);
    const currentFormulaExpr = ref('');
    const currentFormulaDesc = ref('');
    const sandboxResult = ref(null);
    const sandboxVariables = reactive({});
    const savingFormula = ref(false);
    const formulaSavedAlert = ref(false);

    // Targets & Plans
    const employeeTargets = ref([]);

    // Settings
    const bitrixWebhookInput = ref('');
    const bitrixWebhookMasked = ref('');
    const bitrixConnMsg = ref('');
    const bitrixConnSuccess = ref(true);

    // Computed Properties
    const currentPeriod = computed(() => {
      return periods.value.find(p => p.id === selectedPeriodId.value) || null;
    });

    const myCalculation = computed(() => {
      if (!currentResults.value) return null;
      return currentResults.value.find(r => r.user_id === currentUser.value.id) || null;
    });

    const dashboardStats = computed(() => {
      const rows = currentResults.value || [];
      if (rows.length === 0) {
        return { totalBonus: 0, avgKpi: 0, abovePlanCount: 0, totalEmployees: 0 };
      }
      const totalBonus = rows.reduce((acc, r) => acc + (r.bonus_amount || 0), 0);
      const avgKpi = Math.round(rows.reduce((acc, r) => acc + (r.kpi_percent || 0), 0) / rows.length);
      const abovePlanCount = rows.filter(r => (r.kpi_percent || 0) >= 100).length;
      return {
        totalBonus,
        avgKpi,
        abovePlanCount,
        totalEmployees: rows.length
      };
    });

    // Helper: authenticated fetch
    const authFetch = async (url, options = {}) => {
      options.headers = options.headers || {};
      if (authToken.value) {
        if (options.headers instanceof Headers) {
          options.headers.set('Authorization', `Bearer ${authToken.value}`);
        } else {
          options.headers['Authorization'] = `Bearer ${authToken.value}`;
        }
      }
      let resp;
      try {
        resp = await fetch(url, options);
      } catch (e) {
        // Бэкенд не запущен или недоступен: показываем это явно, а не «мертвый» интерфейс
        apiOnline.value = false;
        apiError.value = e && e.message ? e.message : String(e);
        return {
          ok: false,
          status: 0,
          statusText: 'Нет связи с сервером',
          json: async () => ({ detail: 'Нет связи с сервером API. Запустите python run.py и откройте http://127.0.0.1:8000' })
        };
      }
      apiOnline.value = true;
      apiError.value = '';
      if (resp.status === 401) {
        authToken.value = '';
        localStorage.removeItem('kpi_token');
      }
      return resp;
    };

    // Methods
    const refreshIcons = () => {
      nextTick(() => {
        if (window.lucide) {
          window.lucide.createIcons();
        }
      });
    };

    // Всплывающие сообщения показываем собственной плашкой: системный notify() во встроенных
    // и мобильных браузерах часто блокируется, и тогда кажется, что кнопка не работает.
    const notify = (text, type = null) => {
      const message = String(text);
      const kind = type || (/^(Ошибка|Не удалось|Нет связи|Укажите|Введите)/i.test(message) ? 'error' : 'success');
      notice.value = { text: message, type: kind };
      clearTimeout(noticeTimer);
      noticeTimer = setTimeout(() => { notice.value = null; }, 8000);
    };

    // Название периода подставляется по дате начала: «Ноябрь 2026»
    const suggestPeriodName = () => {
      const date = new Date(newPeriodForm.start_date);
      if (isNaN(date.getTime())) return '';
      const month = new Intl.DateTimeFormat('ru-RU', { month: 'long' }).format(date);
      return month.charAt(0).toUpperCase() + month.slice(1) + ' ' + date.getFullYear();
    };

    const openNewPeriodModal = () => {
      periodFormError.value = '';
      if (!newPeriodForm.name.trim()) {
        newPeriodForm.name = suggestPeriodName();
      }
      showNewPeriodModal.value = true;
    };

    const tabClass = (tab) => {
      const active = currentTab.value === tab;
      return [
        'px-3 py-2 rounded-lg text-xs font-semibold flex items-center transition whitespace-nowrap',
        active 
          ? 'bg-blue-600 text-white shadow-sm' 
          : 'text-slate-300 hover:text-white hover:bg-slate-700/60'
      ];
    };

    const formatMoney = (val) => {
      if (val === undefined || val === null || isNaN(val)) return '0 ₽';
      return new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: 'RUB',
        maximumFractionDigits: 0
      }).format(val);
    };

    const formatNumber = (val) => {
      if (val === undefined || val === null || isNaN(val)) return '0';
      return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(val);
    };

    const kpiBadgeClass = (pct) => {
      if (pct >= 100) return 'bg-emerald-100 text-emerald-800 border border-emerald-300';
      if (pct >= 80) return 'bg-amber-100 text-amber-800 border border-amber-300';
      return 'bg-red-100 text-red-800 border border-red-300';
    };

    const periodStatusBadge = (status) => {
      if (status === 'LOCKED') return 'bg-slate-200 text-slate-800';
      if (status === 'CALCULATED') return 'bg-emerald-100 text-emerald-800';
      return 'bg-amber-100 text-amber-800';
    };

    // Load initial data
    const init = async () => {
      try {
        // 1. Users list
        const usersResp = await fetch('/api/auth/users');
        allUsers.value = usersResp.ok ? await usersResp.json() : [];
        if (allUsers.value.length > 0) {
          apiOnline.value = true;
          apiError.value = '';
          const savedUid = localStorage.getItem('kpi_user_id');
          const matchedUser = allUsers.value.find(u => u.id === Number(savedUid));
          selectedUserId.value = matchedUser ? matchedUser.id : allUsers.value[0].id;
          await switchUser(false);
        } else {
          // Бэкенд недоступен: дальше грузить нечего, показываем предупреждение
          apiOnline.value = false;
          apiError.value = 'Сервер API не отвечает на ' + window.location.origin;
          return;
        }

        // 2. Bitrix Status
        const b24Resp = await fetch('/api/auth/bitrix/status');
        if (b24Resp.ok) {
          bitrixStatus.value = await b24Resp.json();
        }

        // 3. Formula Variables Catalog
        const varsResp = await fetch('/api/formulas/variables');
        if (varsResp.ok) {
          variablesCatalog.value = await varsResp.json();
        }

        // 4. Formula Templates & Positions
        const tplResp = await authFetch('/api/formulas/templates');
        if (tplResp.ok) {
          allPositions.value = await tplResp.json();
          if (allPositions.value.length > 0) {
            selectedPositionId.value = allPositions.value[0].position_id;
            loadPositionFormula();
          }
        }

        // 5. Periods
        await loadPeriods();

      } catch (e) {
        console.error('Initialization error:', e);
        apiOnline.value = false;
        apiError.value = e && e.message ? e.message : String(e);
      } finally {
        refreshIcons();
      }
    };

    const retryConnection = async () => {
      apiOnline.value = true;
      apiError.value = '';
      await init();
    };

    const loadPeriods = async () => {
      const resp = await authFetch('/api/periods');
      if (resp.ok) {
        periods.value = await resp.json();
        if (periods.value.length > 0 && !selectedPeriodId.value) {
          selectedPeriodId.value = periods.value[0].id;
        }
        if (selectedPeriodId.value) {
          await loadPeriodData();
        }
      }
      refreshIcons();
    };

    const loadPeriodData = async () => {
      if (!selectedPeriodId.value) return;

      // Load results
      const resResp = await authFetch(`/api/periods/${selectedPeriodId.value}/results`);
      if (resResp.ok) {
        currentResults.value = await resResp.json();
      } else {
        currentResults.value = [];
      }

      // Load targets (if admin or head)
      if (currentUser.value.role !== 'EMPLOYEE') {
        const tResp = await authFetch(`/api/company/periods/${selectedPeriodId.value}/targets`);
        if (tResp.ok) {
          employeeTargets.value = await tResp.json();
        } else {
          employeeTargets.value = [];
        }
      }

      refreshIcons();
    };

    const switchUser = async (reload = true) => {
      try {
        const resp = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: selectedUserId.value })
        });
        if (resp.ok) {
          const data = await resp.json();
          authToken.value = data.token;
          localStorage.setItem('kpi_token', data.token);
          localStorage.setItem('kpi_user_id', String(data.user.id));
          currentUser.value = data.user;

          if (currentUser.value.role === 'EMPLOYEE') {
            currentTab.value = 'my_kpi';
          }
          if (reload) {
            await loadPeriods();
          }
        }
      } catch (e) {
        console.error('Login error:', e);
        apiOnline.value = false;
        apiError.value = e && e.message ? e.message : String(e);
      }
      refreshIcons();
    };

    const toggleMockMode = async () => {
      const nextMode = !bitrixStatus.value.mock_mode;
      try {
        const resp = await authFetch(`/api/auth/bitrix/toggle-mock?enabled=${nextMode}`, { method: 'POST' });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          notify('Ошибка переключения: ' + (err.detail || resp.statusText));
          return;
        }
        const data = await resp.json();
        bitrixStatus.value.mock_mode = data.mock_mode;
      } catch (e) {
        notify('Ошибка запроса: ' + e);
      }
      refreshIcons();
    };

    const triggerCalculation = async (periodId) => {
      calculating.value = true;
      try {
        const resp = await authFetch(`/api/periods/${periodId}/calculate`, { method: 'POST' });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          notify('Ошибка расчета: ' + (err.detail || resp.statusText));
          return;
        }
        const data = await resp.json();
        if (data.warnings && data.warnings.length > 0) {
          console.warn('Предупреждения при расчете:', data.warnings);
          notify('Расчет выполнен с предупреждениями:\n• ' + data.warnings.join('\n• '));
        }
        await loadPeriods();
      } catch (e) {
        notify('Ошибка при выполнении запроса: ' + e);
      } finally {
        calculating.value = false;
        refreshIcons();
      }
    };

    const lockPeriod = async (periodId) => {
      // confirm() может быть недоступен во встроенных браузерах — тогда просто продолжаем
      let confirmed = true;
      try {
        confirmed = confirm('Зафиксировать период? Расчеты будут окончательно заморожены для архива и бухгалтерского отчета.');
      } catch (e) {
        confirmed = true;
      }
      if (!confirmed) return;
      try {
        const resp = await authFetch(`/api/periods/${periodId}/lock`, { method: 'POST' });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          notify('Ошибка фиксации: ' + (err.detail || resp.statusText));
          return;
        }
        await loadPeriods();
      } catch (e) {
        notify('Ошибка: ' + e);
      }
    };

    const exportExcel = async (periodId) => {
      try {
        const resp = await authFetch(`/api/export/periods/${periodId}/excel`);
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          notify('Ошибка экспорта: ' + (err.detail || 'Доступ запрещен'));
          return;
        }
        const blob = await resp.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `KPI_Report_period_${periodId}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      } catch (e) {
        notify('Ошибка скачивания: ' + e);
      }
    };

    const exportCsv = async (periodId) => {
      try {
        const resp = await authFetch(`/api/export/periods/${periodId}/csv`);
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          notify('Ошибка экспорта: ' + (err.detail || 'Доступ запрещен'));
          return;
        }
        const blob = await resp.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `kpi_report_${periodId}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      } catch (e) {
        notify('Ошибка скачивания: ' + e);
      }
    };

    const openResultDetails = (row) => {
      selectedResultModal.value = row;
      refreshIcons();
    };

    // Formula Builder Handlers
    const loadPositionFormula = () => {
      const pos = allPositions.value.find(p => p.position_id === selectedPositionId.value);
      if (pos) {
        currentFormulaExpr.value = pos.formula_expression || '';
        currentFormulaDesc.value = pos.description || '';
        runSandboxTest();
      }
    };

    let lastSelection = { start: 0, end: 0 };
    const trackSelection = (e) => {
      const el = e.target;
      if (el && typeof el.selectionStart === 'number') {
        lastSelection = { start: el.selectionStart, end: el.selectionEnd };
      }
    };

    const insertToken = (token) => {
      const textarea = document.getElementById('formulaTextarea') || document.querySelector('textarea');
      let start = lastSelection.start;
      let end = lastSelection.end;

      if (textarea && typeof textarea.selectionStart === 'number' && document.activeElement === textarea) {
        start = textarea.selectionStart;
        end = textarea.selectionEnd;
      }

      const val = currentFormulaExpr.value || '';
      start = Math.max(0, Math.min(start, val.length));
      end = Math.max(0, Math.min(end, val.length));

      const before = val.substring(0, start);
      const after = val.substring(end);
      const addSpaceBefore = before.length > 0 && !before.endsWith(' ') && !before.endsWith('(');
      const addSpaceAfter = after.length > 0 && !after.startsWith(' ') && !after.startsWith(')');
      const inserted = (addSpaceBefore ? ' ' : '') + token + (addSpaceAfter ? ' ' : '');
      
      currentFormulaExpr.value = before + inserted + after;
      const newPos = start + inserted.length;
      lastSelection = { start: newPos, end: newPos };

      nextTick(() => {
        if (textarea) {
          textarea.focus();
          textarea.setSelectionRange(newPos, newPos);
        }
      });
      runSandboxTest();
    };

    let debounceTimer = null;
    const runSandboxTest = () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(async () => {
        if (!currentFormulaExpr.value.trim()) {
          sandboxResult.value = null;
          return;
        }

        try {
          const resp = await authFetch('/api/formulas/sandbox/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              expression: currentFormulaExpr.value,
              custom_variables: sandboxVariables
            })
          });
          const data = await resp.json();
          sandboxResult.value = data;

          // Merge used variables into local state
          if (data.variables) {
            for (const [k, v] of Object.entries(data.variables)) {
              if (sandboxVariables[k] === undefined) {
                sandboxVariables[k] = v;
              }
            }
          }
        } catch (e) {
          console.error(e);
        } finally {
          refreshIcons();
        }
      }, 250);
    };

    const saveFormulaTemplate = async () => {
      if (!selectedPositionId.value) return;
      savingFormula.value = true;
      try {
        const resp = await authFetch(`/api/formulas/templates/${selectedPositionId.value}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            formula_expression: currentFormulaExpr.value,
            description: currentFormulaDesc.value
          })
        });

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          notify('Ошибка сохранения: ' + (err.detail || resp.statusText));
          return;
        }

        formulaSavedAlert.value = true;
        setTimeout(() => { formulaSavedAlert.value = false; }, 3000);

        // Update list item
        const item = allPositions.value.find(p => p.position_id === selectedPositionId.value);
        if (item) {
          item.formula_expression = currentFormulaExpr.value;
          item.description = currentFormulaDesc.value;
        }
      } catch (e) {
        notify('Ошибка при сохранении: ' + e);
      } finally {
        savingFormula.value = false;
        refreshIcons();
      }
    };

    const saveEmployeeTarget = async (target) => {
      try {
        const resp = await authFetch(`/api/company/periods/${selectedPeriodId.value}/targets/${target.user_id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            base_rate: target.base_rate,
            plan_sales: target.plan_sales,
            plan_tasks: target.plan_tasks,
            target_calls: target.target_calls,
            quality_score: target.quality_score
          })
        });
        if (resp.ok) {
          notify('План для сотрудника успешно обновлен!');
        } else {
          const err = await resp.json().catch(() => ({}));
          notify('Ошибка сохранения плана: ' + (err.detail || resp.statusText));
        }
      } catch (e) {
        notify('Ошибка сохранения плана: ' + e);
      }
    };

    const submitNewPeriod = async () => {
      periodFormError.value = '';

      // Название не обязательно вводить вручную — подставляем по дате начала
      if (!newPeriodForm.name.trim()) {
        newPeriodForm.name = suggestPeriodName();
      }
      if (!newPeriodForm.name.trim()) {
        periodFormError.value = 'Укажите название периода.';
        return;
      }
      if (!newPeriodForm.start_date || !newPeriodForm.end_date) {
        periodFormError.value = 'Укажите даты начала и окончания периода.';
        return;
      }
      if (newPeriodForm.start_date > newPeriodForm.end_date) {
        periodFormError.value = 'Дата начала не может быть позже даты окончания.';
        return;
      }

      creating.value = true;
      try {
        const resp = await authFetch('/api/periods', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(newPeriodForm)
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          const detail = Array.isArray(err.detail)
            ? err.detail.map(item => item.msg).join('; ')
            : (err.detail || resp.statusText);
          periodFormError.value = 'Не удалось создать период: ' + detail;
          return;
        }
        const created = await resp.json();
        showNewPeriodModal.value = false;
        notify('Период «' + created.name + '» создан');
        selectedPeriodId.value = created.id;
        await loadPeriods();
      } catch (e) {
        periodFormError.value = 'Ошибка запроса: ' + e;
      } finally {
        creating.value = false;
        refreshIcons();
      }
    };

    const loadBitrixSettings = async () => {
      if (currentUser.value.role !== 'ADMIN') return;
      try {
        const resp = await authFetch('/api/settings/bitrix');
        if (resp.ok) {
          const data = await resp.json();
          bitrixWebhookMasked.value = data.webhook_url_masked || '';
          bitrixStatus.value.mock_mode = data.mock_mode;
          bitrixStatus.value.is_configured = data.is_configured;
          // Do NOT set bitrixWebhookInput to masked URL to avoid saving mask
        }
      } catch (e) {
        console.error(e);
      }
    };

    const saveBitrixSettings = async () => {
      const urlToSave = bitrixWebhookInput.value.trim();
      if (!urlToSave) {
        notify('Введите новый URL вебхука для сохранения или оставьте поле пустым.');
        return;
      }
      try {
        const resp = await authFetch('/api/settings/bitrix', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ webhook_url: urlToSave })
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          bitrixConnSuccess.value = false;
          bitrixConnMsg.value = 'Ошибка: ' + (err.detail || 'Некорректный URL');
          return;
        }
        const data = await resp.json();
        bitrixWebhookMasked.value = data.webhook_url_masked || '';
        bitrixWebhookInput.value = '';
        bitrixConnSuccess.value = true;
        bitrixConnMsg.value = 'Настройки успешно сохранены!';
        setTimeout(() => { bitrixConnMsg.value = ''; }, 4000);
      } catch (e) {
        bitrixConnSuccess.value = false;
        bitrixConnMsg.value = 'Ошибка: ' + e;
      }
    };

    const testBitrixConnection = async () => {
      try {
        const resp = await authFetch('/api/settings/bitrix/test', { method: 'POST' });
        const data = await resp.json();
        if (data.ok) {
          bitrixConnSuccess.value = true;
          bitrixConnMsg.value = data.message || `Соединение успешно (${data.elapsed_ms} мс)!`;
        } else {
          bitrixConnSuccess.value = false;
          bitrixConnMsg.value = `Ошибка: ${data.error || 'Сбой соединения'}`;
        }
      } catch (e) {
        bitrixConnSuccess.value = false;
        bitrixConnMsg.value = 'Ошибка: ' + e;
      }
      setTimeout(() => { bitrixConnMsg.value = ''; }, 6000);
    };

    onMounted(() => {
      init();
    });

    return {
      currentTab,
      allUsers,
      selectedUserId,
      currentUser,
      bitrixStatus,
      apiOnline,
      apiError,
      periods,
      selectedPeriodId,
      currentPeriod,
      currentResults,
      dashboardStats,
      calculating,
      selectedResultModal,
      showNewPeriodModal,
      newPeriodForm,
      periodFormError,
      creating,
      notice,
      variablesCatalog,
      allPositions,
      selectedPositionId,
      currentFormulaExpr,
      currentFormulaDesc,
      sandboxResult,
      sandboxVariables,
      savingFormula,
      formulaSavedAlert,
      employeeTargets,
      myCalculation,
      bitrixWebhookInput,
      bitrixWebhookMasked,
      bitrixConnMsg,
      bitrixConnSuccess,
      tabClass,
      formatMoney,
      formatNumber,
      kpiBadgeClass,
      periodStatusBadge,
      switchUser,
      toggleMockMode,
      triggerCalculation,
      lockPeriod,
      exportExcel,
      exportCsv,
      openResultDetails,
      loadPositionFormula,
      insertToken,
      trackSelection,
      runSandboxTest,
      saveFormulaTemplate,
      saveEmployeeTarget,
      submitNewPeriod,
      loadBitrixSettings,
      saveBitrixSettings,
      testBitrixConnection,
      loadPeriodData,
      retryConnection,
      openNewPeriodModal
    };
  }
});

app.mount('#app');
