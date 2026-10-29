(function () {
  'use strict';
  const DATA = JSON.parse(document.getElementById('simulation-data').textContent);
  const $ = function (id) { return document.getElementById(id); };
  const NS = 'http://www.w3.org/2000/svg';
  const COLORS = {DE_BE_13: '#783c91', DE_BE_48: '#168e93', DE_BE_50: '#d88f31', DE_BE_65: '#5685be'};
  const NAMES = {
    pending: '尚未释放', wait_vehicle_in: '等待进站车辆', empty_in: '空车前往接货',
    load_in: '进站装载', loaded_in: '载货进站', unload_in: '进站卸载',
    wait_equipment: '设备排队', processing: '设备加工', wait_vehicle_out: '等待出站车辆',
    empty_out: '空车前往设备', load_out: '出站装载', loaded_out: '载货出站',
    unload_out: '出站卸载', completed: '区域任务完成'
  };
  const STAGE = function (state) {
    if (state.indexOf('wait') === 0) return 'wait';
    if (state.indexOf('empty') === 0) return 'empty';
    if (state.indexOf('loaded') === 0) return 'loaded';
    if (state === 'processing') return 'processing';
    return 'handling';
  };
  const STAGE_COLORS = {wait: '#d3cbd9', empty: '#8a8193', loaded: '#168e93', handling: '#dfb77c', processing: '#783c91'};
  const fmt = function (n, digits) { return Number(n || 0).toLocaleString('zh-CN', {minimumFractionDigits: digits === undefined ? 2 : digits, maximumFractionDigits: digits === undefined ? 2 : digits}); };
  const esc = function (s) { return String(s).replace(/[&<>"']/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); };
  const svg = function (tag, attributes, text) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attributes || {}).forEach(function (entry) { node.setAttribute(entry[0], entry[1]); });
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const state = {scenario: DATA.scenarios[0].id, time: 0, speed: 30, playing: false, task: '', view: DATA.factory ? 'factory' : 'focus', showOtherVehicles: false, zoom: 1, cameraX: 350, cameraY: 165};
  let frame = null, lastFrame = null, lastDraw = 0, views = {}, timelineScale = null;
  const slots = new Map(DATA.slots.map(function (s) { return [s.slot_name, s]; }));
  const pathCache = new Map();
  let cases = {}, selectedTasks = {}, taskMaps = {}, orderedEvents = {};

  function pathInfo(key) {
    if (pathCache.has(key)) return pathCache.get(key);
    const path = DATA.network.paths[key];
    if (!path) return {points: [], cumulative: [0], length: 0};
    const points = path.points;
    const cumulative = [0];
    for (let i = 1; i < points.length; i++) cumulative.push(cumulative[i - 1] + Math.abs(points[i][0] - points[i - 1][0]) + Math.abs(points[i][1] - points[i - 1][1]));
    const result = {points: points, cumulative: cumulative, length: cumulative[cumulative.length - 1]};
    pathCache.set(key, result);
    return result;
  }
  function pointAlong(key, fraction) {
    const p = pathInfo(key);
    if (!p.points.length) return [0, 0];
    const distance = Math.max(0, Math.min(1, fraction)) * p.length;
    for (let i = 1; i < p.cumulative.length; i++) {
      if (p.cumulative[i] >= distance) {
        const span = p.cumulative[i] - p.cumulative[i - 1];
        const r = span ? (distance - p.cumulative[i - 1]) / span : 0;
        return [p.points[i - 1][0] + (p.points[i][0] - p.points[i - 1][0]) * r, p.points[i - 1][1] + (p.points[i][1] - p.points[i - 1][1]) * r];
      }
    }
    return p.points[p.points.length - 1];
  }
  function scenario() { return DATA.scenarios.find(function (s) { return s.id === state.scenario; }); }
  function duration() { return Math.max(cases.before.metrics.makespan_min, cases.after.metrics.makespan_min); }
  function taskState(task, time) {
    if (!task || time < task.release) return {state: 'pending'};
    if (time >= task.completed_at) return {state: 'completed'};
    return task.timeline.find(function (s) { return time >= s.t0 && time < s.t1; }) || {state: 'pending'};
  }
  function elapsed(task, states, time) {
    return task.timeline.reduce(function (sum, s) { return sum + (states(s.state) ? Math.max(0, Math.min(time, s.t1) - s.t0) : 0); }, 0);
  }
  function fit(points) {
    if (!points.length) points = [[0, 0], [250, 150]];
    const xs = points.map(function (p) { return p[0]; }), ys = points.map(function (p) { return p[1]; });
    const x0 = Math.min.apply(null, xs) - 10, x1 = Math.max.apply(null, xs) + 10;
    const y0 = Math.min.apply(null, ys) - 12, y1 = Math.max.apply(null, ys) + 12;
    const scale = Math.min(650 / Math.max(1, x1 - x0), 272 / Math.max(1, y1 - y0));
    return function (p) { return [25 + (650 - (x1 - x0) * scale) / 2 + (p[0] - x0) * scale, 18 + (272 - (y1 - y0) * scale) / 2 + (y1 - p[1]) * scale]; };
  }
  function polyline(key, projection) {
    return pathInfo(key).points.map(function (p, i) { const q = projection(p); return (i ? 'L' : 'M') + q[0].toFixed(2) + ',' + q[1].toFixed(2); }).join(' ');
  }
  function pathKeys(task) {
    return Array.from(new Set(task.timeline.filter(function (s) { return s.path && s.state.indexOf('loaded') === 0; }).map(function (s) { return s.path; })));
  }
  function taskPose(task, status, time) {
    const incoming = task.timeline.find(function (s) { return s.state === 'loaded_in'; });
    const outgoing = task.timeline.find(function (s) { return s.state === 'loaded_out'; });
    if (status.path && status.state.indexOf('loaded') === 0) return {path: status.path, fraction: (time - status.t0) / Math.max(.000001, status.t1 - status.t0)};
    if (['wait_vehicle_in', 'empty_in', 'load_in'].includes(status.state) && incoming) return {path: incoming.path, fraction: 0};
    if (status.state === 'unload_out' && outgoing) return {path: outgoing.path, fraction: 1};
    if (outgoing && ['load_out', 'empty_out', 'wait_vehicle_out', 'processing', 'wait_equipment'].includes(status.state)) return {path: outgoing.path, fraction: 0};
    if (incoming && status.state === 'unload_in') return {path: incoming.path, fraction: 1};
    return null;
  }
  function applyCamera() {
    const width = 700 / state.zoom, height = 330 / state.zoom;
    state.cameraX = Math.max(width / 2, Math.min(700 - width / 2, state.cameraX));
    state.cameraY = Math.max(height / 2, Math.min(330 - height / 2, state.cameraY));
    const box = [state.cameraX - width / 2, state.cameraY - height / 2, width, height].join(' ');
    ['before', 'after'].forEach(function (name) { $('map-' + name).setAttribute('viewBox', box); });
    $('zoom-label').textContent = fmt(state.zoom, 1) + '×';
    $('zoom-out').disabled = state.zoom <= 1;
    $('zoom-in').disabled = state.zoom >= 8;
    ['pan-left', 'pan-right', 'pan-up', 'pan-down'].forEach(function (id) { $(id).disabled = state.zoom <= 1; });
  }
  function setZoom(value) {
    const zoom = Number(value);
    if (!Number.isFinite(zoom) || zoom <= 0) throw new Error('Camera zoom must be positive');
    state.zoom = Math.max(1, Math.min(8, zoom)); applyCamera(); return state.zoom;
  }
  function resetCamera() { state.zoom = 1; state.cameraX = 350; state.cameraY = 165; applyCamera(); }
  function panCamera(dx, dy) {
    state.cameraX += dx * 700 / state.zoom * .22;
    state.cameraY += dy * 330 / state.zoom * .22;
    applyCamera();
  }
  function setView(view) {
    if (!['factory', 'local', 'focus', 'all'].includes(view)) throw new Error('Unknown map view: ' + view);
    state.view = view; $('map-view').value = view;
    state.zoom = 1; state.cameraX = 350; state.cameraY = 165;
    initMaps(); draw();
  }
  function projectedBox(box, project) {
    const a = project([box.x0, box.y1]), b = project([box.x1, box.y0]);
    return {x: a[0], y: a[1], width: Math.max(.3, b[0] - a[0]), height: Math.max(.3, b[1] - a[1])};
  }
  function initMaps() {
    const points = [];
    if (state.view === 'factory' && DATA.factory) {
      points.push.apply(points, DATA.network.nodes);
      DATA.factory.equipment.forEach(function (e) { points.push([e.x-e.width/2,e.y-e.height/2],[e.x+e.width/2,e.y+e.height/2]); });
      DATA.factory.bays.forEach(function (b) { points.push([b.x0,b.y0],[b.x1,b.y1]); });
    } else if (state.view === 'local') {
      DATA.slots.forEach(function (s) { points.push([s.position_x / 1000-s.width/2000, s.position_y/1000-s.height/2000],[s.position_x/1000+s.width/2000,s.position_y/1000+s.height/2000]); });
    } else if (state.view === 'all') Object.values(DATA.network.paths).forEach(function (p) { points.push.apply(points, p.points); });
    else ['before', 'after'].forEach(function (name) { selectedTasks[name].timeline.forEach(function (s) { if (s.path) points.push.apply(points, pathInfo(s.path).points); }); });
    DATA.slots.forEach(function (s) { points.push([s.position_x / 1000, s.position_y / 1000]); });
    const project = fit(points);
    ['before', 'after'].forEach(function (name) {
      const map = $('map-' + name), local = $('local-' + name);
      map.replaceChildren(); local.replaceChildren(); local.setAttribute('viewBox', '0 0 220 340');
      const color = name === 'before' ? '#783c91' : '#168e93';
      const factorySlots = new Map();
      if (DATA.factory) {
        const bayLayer = svg('g', {'data-role': 'factory-bays'});
        DATA.factory.bays.forEach(function (bay) {
          const box = projectedBox(bay, project), active = bay.name === 'A2' || bay.name === 'A3';
          const group = svg('g', {'data-role': 'factory-bay', 'data-bay': bay.name, 'data-simulated': String(active), role: 'button', tabindex: '0', 'aria-label': bay.name + (active ? '，进入 A2/A3 局部' : '，居中放大布局区域')});
          group.append(svg('rect', {x: box.x - 1.5, y: box.y - 1.5, width: box.width + 3, height: box.height + 3, fill: active ? color : '#8b8196', 'fill-opacity': active ? .07 : .014, stroke: active ? color : '#dcd5e2', 'stroke-width': active ? 1.4 : .35, 'stroke-dasharray': active ? 'none' : '2 3'}));
          group.append(svg('title', {}, bay.name + ' · ' + bay.count + ' 个设备/设施对象；设备与轨道包络示意，非物理边界' + (active ? '；48 台生产设备中的所属部分参与仿真' : '；仅静态布局背景')));
          function enterBay() {
            if (active) { setView('local'); return; }
            state.cameraX = box.x + box.width / 2; state.cameraY = box.y + box.height / 2; setZoom(4);
          }
          group.addEventListener('click', enterBay);
          group.addEventListener('keydown', function (event) { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); enterBay(); } });
          bayLayer.append(group);
        });
        map.append(bayLayer);
      }
      const background = svg('g', {'aria-hidden': 'true'});
      let d = '';
      DATA.network.rails.forEach(function (rail) {
        const a = project(DATA.network.nodes[rail[0]]), b = project(DATA.network.nodes[rail[1]]);
        if (a[0] < -20 && b[0] < -20 || a[0] > 720 && b[0] > 720 || a[1] < -20 && b[1] < -20 || a[1] > 350 && b[1] > 350) return;
        d += 'M' + a[0].toFixed(1) + ',' + a[1].toFixed(1) + 'L' + b[0].toFixed(1) + ',' + b[1].toFixed(1);
      });
      background.append(svg('path', {d: d, fill: 'none', stroke: '#e1dbe6', 'stroke-width': .65}));
      map.append(background);
      if (DATA.factory) {
        const equipmentLayer = svg('g', {'data-role': 'factory-equipment-layer'});
        DATA.factory.equipment.forEach(function (e) {
          const slot = slots.get(e.name), active = Boolean(slot);
          const group = active ? name === 'before' ? slot.original_group : slot.optimized_group : e.group;
          const box = projectedBox({x0:e.x-e.width/2,y0:e.y-e.height/2,x1:e.x+e.width/2,y1:e.y+e.height/2}, project);
          const fixed = ['COMMIT','COMPLETE','STOCKER'].includes(e.group);
          const equipment = active ? (name === 'before' ? slot.old_equipment : slot.new_equipment) : e.name;
          const mark = svg('rect', {x:box.x,y:box.y,width:box.width,height:box.height,fill:active ? COLORS[group] : fixed ? '#bac7d0' : '#d4cedb',stroke:active ? '#fff' : 'none','stroke-width':.2,opacity:active ? .9 : .65,
            'data-role':'factory-equipment','data-equipment':equipment,'data-slot':e.name,'data-bay':e.bay,'data-simulated':String(active)});
          const title = svg('title', {}, equipment + ' · ' + group + ' · ' + e.bay + (active ? '；A2/A3 动态仿真设备' : '；静态布局背景，未仿真加工'));
          mark.append(title); equipmentLayer.append(mark);
          if (active) factorySlots.set(e.name,{rect:mark,title:title,group:group,equipment:equipment});
        });
        map.append(equipmentLayer);
        const labelLayer = svg('g', {'data-role':'factory-labels','pointer-events':'none'});
        DATA.factory.bays.forEach(function (bay) {
          const box=projectedBox(bay,project), active=bay.name==='A2'||bay.name==='A3';
          if (bay.name.startsWith('InterBay')) return;
          labelLayer.append(svg('text',{x:box.x+box.width/2,y:box.y-4,'font-size':active?12:10,'font-weight':active?700:400,'text-anchor':'middle',fill:active?color:'#81768a'},bay.name));
        });
        map.append(labelLayer);
      }
      const selected = selectedTasks[name];
      selected.timeline.forEach(function (segment) {
        if (!segment.path || segment.state.indexOf('loaded') !== 0) return;
        map.append(svg('path', {d: polyline(segment.path, project), fill: 'none', stroke: color, 'stroke-width': 2, 'stroke-dasharray': segment.state === 'loaded_out' ? '7 4' : 'none', opacity: .7, 'data-role': 'planned-route', 'data-path': segment.path, 'data-task-id': selected.task_id, 'data-phase': segment.state}));
      });
      pathKeys(selected).forEach(function (key, i) {
        const p = pathInfo(key).points;
        if (!p.length) return;
        [p[0], p[p.length - 1]].forEach(function (xy, j) {
          const q = project(xy);
          map.append(svg('circle', {cx: q[0], cy: q[1], r: 3, fill: color}));
          const label = key.split('>')[j];
          const isSlot = slots.has(label);
          if (!isSlot) map.append(svg('text', {x: Math.max(10, Math.min(595, q[0] + 6)), y: q[1] + (i ? 17 : -8), 'font-size': 12, fill: '#554e5e'}, label));
        });
      });
      const activeRouteLayer = svg('g', {'data-role': 'active-routes'}), vehicleLayer = svg('g', {}), lotLayer = svg('g', {});
      map.append(activeRouteLayer, vehicleLayer, lotLayer);
      const localSlots = new Map();
      DATA.slots.forEach(function (s) {
        const x = 30 + (s.position_x / 1000 - 13) * 4.2, y = 320 - (s.position_y / 1000 - 72) * 4.2;
        const w = s.width / 1000 * 4.2, h = s.height / 1000 * 4.2;
        const g = svg('g', {});
        const group = name === 'before' ? s.original_group : s.optimized_group;
        const rect = svg('rect', {x: x - w / 2, y: y - h / 2, width: w, height: h, fill: COLORS[group], stroke: '#fff', 'stroke-width': .5});
        const title = svg('title', {}, s.id + ' · ' + group);
        const queue = svg('text', {x: x + w / 2 + 2, y: y + 4, 'font-size': 11, fill: '#27242f', 'font-weight': 600});
        rect.append(title); g.append(rect, queue); local.append(g);
        localSlots.set(s.slot_name, {g: g, rect: rect, queue: queue, x: x, y: y, title: title, group: group});
      });
      local.append(svg('text', {x: 65, y: 25, 'font-size': 15, 'text-anchor': 'middle', fill: '#716b78'}, 'A2'), svg('text', {x: 130, y: 25, 'font-size': 15, 'text-anchor': 'middle', fill: '#716b78'}, 'A3'));
      views[name] = {project: project, activeRouteLayer: activeRouteLayer, vehicleLayer: vehicleLayer, lotLayer: lotLayer, localSlots: localSlots, factorySlots: factorySlots};
    });
    const factory = DATA.factory;
    $('factory-summary').textContent = factory ? '全厂布局：' + factory.counts.equipment + ' 个设备/设施对象（' + factory.counts.production + ' 台生产设备、' + factory.counts.fixed_amhs + ' 个固定 AMHS 设施），' + factory.counts.bays + ' 个 Bay。仅 A2/A3 的 48 台生产设备参与动态仿真；灰色区域为静态背景。' : '仅 A2/A3 的设备参与动态仿真。';
    applyCamera();
  }
  function currentData(name) {
    const count = {released: 0, completed: 0, processing: 0, equipmentQueue: 0, vehicleQueue: 0};
    const busy = new Map(), queues = new Map();
    cases[name].tasks.forEach(function (task) {
      if (state.time >= task.release) count.released++;
      const status = taskState(task, state.time).state;
      if (status === 'completed') count.completed++;
      else if (status === 'processing') { count.processing++; busy.set(task.slot, task.task_id); }
      else if (status === 'wait_equipment') { count.equipmentQueue++; queues.set(task.slot, (queues.get(task.slot) || 0) + 1); }
      else if (status.indexOf('wait_vehicle') === 0) count.vehicleQueue++;
    });
    return {count: count, busy: busy, queues: queues};
  }
  function renderVehicles(name) {
    const view = views[name], layer = view.vehicleLayer; layer.replaceChildren(); view.activeRouteLayer.replaceChildren();
    let busy = 0, shown = 0;
    cases[name].vehicles.forEach(function (vehicle) {
      const active = vehicle.legs.find(function (leg) { return state.time >= leg.t0 && state.time < leg.t1; });
      const occupied = vehicle.busy_intervals.find(function (x) { return state.time >= x.t0 && state.time < x.t1; });
      if (occupied) busy++;
      let key, fraction, moving = false, loaded = false, taskID = '';
      if (active) { key = active.path; fraction = (state.time - active.t0) / (active.t1 - active.t0); moving = true; loaded = active.loaded; taskID = active.task_id; }
      else {
        taskID = occupied ? occupied.task_id : '';
        const currentTask = taskMaps[name].get(taskID), status = currentTask && taskState(currentTask, state.time);
        const carryingLeg = occupied && vehicle.legs.find(function (leg) { return leg.task_id === taskID && leg.loaded && (status && status.state.endsWith('_in') ? leg.phase === 'in' : leg.phase === 'out'); });
        if (carryingLeg && status && (status.state.indexOf('load_') === 0 || status.state.indexOf('unload_') === 0)) {
          key = carryingLeg.path; fraction = status.state.indexOf('unload_') === 0 ? 1 : 0;
          loaded = status.state.indexOf('unload_') === 0;
        } else {
          const past = vehicle.legs.filter(function (leg) { return leg.t1 <= state.time; });
          if (past.length) { key = past[past.length - 1].path; fraction = 1; }
          else if (vehicle.legs.length) { key = vehicle.legs[0].path; fraction = 0; }
        }
      }
      const chosen = taskID === state.task;
      if (!chosen && !state.showOtherVehicles) return;
      if (!key) return;
      shown++;
      if (moving) {
        const color = chosen ? (loaded ? (name === 'before' ? '#783c91' : '#168e93') : '#716b78') : '#aaa2b0';
        view.activeRouteLayer.append(svg('path', {d: polyline(key, view.project), fill: 'none', stroke: color, 'stroke-width': chosen ? 3 : 1, 'stroke-dasharray': loaded ? active.phase === 'out' ? '7 4' : 'none' : '2 5', opacity: chosen ? .95 : .3, 'data-role': chosen ? 'active-route' : 'other-route', 'data-path': key, 'data-task-id': taskID, 'data-loaded': String(loaded), 'data-phase': active.phase}));
      }
      const world = pointAlong(key, fraction), xy = view.project(world);
      const marker = svg('circle', {cx: xy[0], cy: xy[1], r: chosen ? 6.5 : 3.5, fill: loaded ? '#27242f' : '#fff', stroke: chosen ? '#d88f31' : '#554e5e', 'stroke-width': chosen ? 2.5 : 1.2, opacity: chosen ? 1 : .25,
        'data-role': 'vehicle-marker', 'data-vehicle-id': vehicle.vehicle_id, 'data-path': key, 'data-task-id': taskID, 'data-fraction': fraction, 'data-world-x': world[0], 'data-world-y': world[1], 'data-selected': String(chosen), 'data-loaded': String(loaded), 'data-moving': String(moving)});
      marker.append(svg('title', {}, vehicle.vehicle_id + ' · ' + (moving ? loaded ? '载货行驶' : '空驶接货' : occupied ? loaded ? '卸载' : '装载' : '空闲') + (taskID ? ' · ' + taskID : '') + (chosen ? ' · 所选批次' : ' · 其他任务车辆')));
      layer.append(marker);
      if (chosen) layer.append(svg('text', {x: xy[0] + 9, y: xy[1] - 7, 'font-size': 12, fill: '#754e19', 'font-weight': 600}, vehicle.vehicle_id));
    });
    $('live-' + name).textContent = busy + ' / ' + cases[name].vehicles.length + ' 辆车占用 · 显示 ' + shown + ' 辆';
    const status = taskState(selectedTasks[name], state.time);
    $('route-status-' + name).textContent = status.state.indexOf('empty') === 0 ? '当前为空车接货：灰色点线是小车的接货路线，物料仍在接货端口。' : status.state.indexOf('loaded') === 0 ? '当前为载货运输：所选车辆与物料沿同一条彩色规划路线前进。' : '所选物料：' + NAMES[status.state] + '。彩色线保留入程与出程规划；当前没有所选批次的行驶车辆。';
  }
  function renderTask(name, current) {
    const task = selectedTasks[name], status = taskState(task, state.time), view = views[name];
    const equipment = task.equipment || task.slot;
    const waitCar = elapsed(task, function (s) { return s.indexOf('wait_vehicle') === 0; }, state.time);
    const waitMachine = elapsed(task, function (s) { return s === 'wait_equipment'; }, state.time);
    const loaded = elapsed(task, function (s) { return s.indexOf('loaded') === 0; }, state.time);
    const process = elapsed(task, function (s) { return s === 'processing'; }, state.time);
    $('task-' + name).innerHTML = '<h3>' + esc(task.task_id) + '</h3><div class="task-state">' + NAMES[status.state] + '</div><dl><dt>产品 / 工序</dt><dd>' + esc(task.part) + ' / 第 ' + task.step + ' 步</dd><dt>加工设备</dt><dd>' + esc(equipment) + ' · ' + esc(task.slot) + '</dd><dt>本机状态</dt><dd>' + (current.busy.has(task.slot) ? '加工中' : '空闲') + ' · ' + (current.queues.get(task.slot) || 0) + ' 批排队</dd><dt>固定源 / 目标</dt><dd>' + esc(task.source) + ' → ' + esc(task.target) + '</dd><dt>当前车辆</dt><dd>' + esc(status.vehicle_id || '—') + '</dd></dl><div class="task-counters"><div><span>累计等车</span><b>' + fmt(waitCar) + ' min</b></div><div><span>累计等设备</span><b>' + fmt(waitMachine) + ' min</b></div><div><span>累计载货运输</span><b>' + fmt(loaded) + ' min</b></div><div><span>累计加工</span><b>' + fmt(process) + ' min</b></div></div>';
    view.lotLayer.replaceChildren();
    if (status.state === 'pending' || status.state === 'completed') return;
    const pose = taskPose(task, status, state.time);
    if (pose) {
      const world = pointAlong(pose.path, pose.fraction), xy = view.project(world);
      view.lotLayer.append(svg('rect', {x: xy[0] - 4, y: xy[1] - 4, width: 8, height: 8, fill: '#d88f31', stroke: '#fff', 'stroke-width': 1,
        'data-role': 'lot-marker', 'data-task-id': task.task_id, 'data-state': status.state, 'data-path': pose.path, 'data-fraction': pose.fraction, 'data-world-x': world[0], 'data-world-y': world[1]}));
      view.lotLayer.append(svg('text', {x: Math.max(5, Math.min(600, xy[0] + 8)), y: xy[1] + 18, 'font-size': 11, fill: '#754e19'}, '所选物料'));
    }
  }
  function renderCase(name) {
    const current = currentData(name), c = current.count;
    $('stats-' + name).innerHTML = [['已释放', c.released], ['已完成', c.completed], ['加工中', c.processing], ['等车 / 等设备', c.vehicleQueue + ' / ' + c.equipmentQueue]].map(function (x) { return '<span>' + x[0] + '<strong>' + x[1] + '</strong></span>'; }).join('');
    views[name].localSlots.forEach(function (mark, slot) {
      const occupied = current.busy.has(slot), queue = current.queues.get(slot) || 0, selected = slot === selectedTasks[name].slot;
      mark.rect.setAttribute('stroke', occupied ? '#27242f' : selected ? '#d88f31' : '#fff');
      mark.rect.setAttribute('stroke-width', occupied ? 2.5 : selected ? 2 : .5);
      mark.rect.setAttribute('opacity', occupied || selected ? 1 : .65);
      mark.queue.textContent = queue ? String(queue) : '';
      mark.title.textContent = slot + ' · ' + mark.group + ' · ' + (occupied ? '加工中' : '空闲') + ' · 等待 ' + queue + ' 批';
    });
    views[name].factorySlots.forEach(function (mark, slot) {
      const occupied=current.busy.has(slot),queue=current.queues.get(slot)||0,selected=slot===selectedTasks[name].slot;
      mark.rect.setAttribute('stroke',occupied?'#27242f':selected?'#d88f31':'#fff');
      mark.rect.setAttribute('stroke-width',occupied?1.4:selected?1.2:.2);
      mark.rect.setAttribute('opacity',occupied||selected?1:.8);
      mark.title.textContent=mark.equipment+' · '+mark.group+' · '+(occupied?'加工中':'空闲')+' · 等待 '+queue+' 批；仅 A2/A3 动态仿真';
    });
    renderVehicles(name); renderTask(name, current); renderEvents(name);
  }
  function timelineGeometry() {
    const before = selectedTasks.before, after = selectedTasks.after;
    return {start: Math.min(before.release, after.release), end: Math.max(before.completed_at, after.completed_at)};
  }
  function initTimeline() {
    const canvasWidth = Math.max(250, $('timelines').clientWidth || 1200), left = canvasWidth < 500 ? 75 : 105, right = canvasWidth - 10;
    const timeline = svg('svg', {viewBox: '0 0 ' + canvasWidth + ' 145', class: 'task-timeline', role: 'img', 'aria-label': '所选批次参考和优化布局的等待、搬运与加工时间线'});
    const bounds = timelineGeometry(), width = Math.max(.01, bounds.end - bounds.start);
    const x = function (t) { return left + (t - bounds.start) / width * (right - left); };
    timelineScale = {left: left, right: right, project: x};
    ['before', 'after'].forEach(function (name, row) {
      const task = selectedTasks[name], y = 24 + row * 43;
      timeline.append(svg('text', {x: 0, y: y + 15, 'font-size': 15, fill: '#716b78'}, name === 'before' ? '参考布局' : 'MILP 布局'));
      task.timeline.forEach(function (segment) {
        if (segment.t1 <= segment.t0) return;
        const rect = svg('rect', {x: x(segment.t0), y: y, width: Math.max(.4, x(segment.t1) - x(segment.t0)), height: 22, fill: STAGE_COLORS[STAGE(segment.state)]});
        const label = NAMES[segment.state] + ': ' + fmt(segment.t0) + '–' + fmt(segment.t1) + ' min（' + fmt(segment.t1 - segment.t0) + ' min）';
        rect.append(svg('title', {}, label));
        rect.addEventListener('click', function () { setTime(segment.t0); });
        timeline.append(rect);
      });
    });
    (canvasWidth < 600 ? [0, .5, 1] : [0, .25, .5, .75, 1]).forEach(function (ratio) {
      const t = bounds.start + width * ratio;
      timeline.append(svg('text', {x: x(t), y: 126, 'font-size': 12, 'text-anchor': ratio === 1 ? 'end' : ratio === 0 ? 'start' : 'middle', fill: '#716b78'}, fmt(t, 1) + ' min'));
    });
    timeline.append(svg('line', {id: 'timeline-pointer', x1: left, x2: left, y1: 15, y2: 97, stroke: '#27242f', 'stroke-width': 1.5}));
    $('timelines').replaceChildren(timeline);
  }
  function renderTimelinePointer() {
    const bounds = timelineGeometry(), x = timelineScale.project(state.time), bounded = Math.max(timelineScale.left, Math.min(timelineScale.right, x));
    const pointer = $('timeline-pointer');
    if (pointer) { pointer.setAttribute('x1', bounded); pointer.setAttribute('x2', bounded); pointer.setAttribute('opacity', state.time < bounds.start || state.time > bounds.end ? .25 : 1); }
  }
  function renderEvents(name) {
    const task = selectedTasks[name], items = task.timeline.map(function (segment) { return {time: segment.t0, text: NAMES[segment.state] + (segment.vehicle_id ? ' · ' + segment.vehicle_id : '')}; });
    items.push({time: task.completed_at, text: '区域任务完成'});
    let active = -1; items.forEach(function (item, i) { if (item.time <= state.time) active = i; });
    $('events-' + name).innerHTML = items.map(function (item, i) { return '<li class="' + (i > active ? 'future' : i === active ? 'current' : '') + '"><time>' + fmt(item.time) + '</time><span>' + esc(item.text) + '</span></li>'; }).join('');
  }
  const METRICS = [
    ['loaded_distance_raw', '载货运输总距离', 1 / 1000, '千原始单位', false],
    ['empty_distance_raw', '空车行驶总距离', 1 / 1000, '千原始单位', false],
    ['mean_transport_min', '平均搬运请求完成时间', 1, 'min', false],
    ['p95_transport_min', 'P95 搬运请求完成时间', 1, 'min', false],
    ['mean_wait_vehicle_min', '每批平均等车时间（进出合计）', 1, 'min', false],
    ['mean_wait_equipment_min', '每批平均等设备时间', 1, 'min', false],
    ['mean_sojourn_min', '每批平均区域停留时间', 1, 'min', false],
    ['vehicle_utilization', '车辆忙碌率（全程）', 100, '%', null],
    ['completed_by_horizon', '7 天窗口内完成的区域任务', 1, '批', true],
    ['wip_at_horizon', '7 天窗口末未完成的已释放任务', 1, '批', false],
    ['completed', '跑至结束完成的区域任务', 1, '批', true],
    ['makespan_min', '全部任务完成时刻', 1, 'min', false]
  ];
  function metricValue(metrics, key) {
    const value = metrics[key];
    if (typeof value === 'number') return value;
    if (key === 'vehicle_utilization' && value && typeof value === 'object') {
      const vals = Object.values(value); return vals.reduce(function (a, b) { return a + b; }, 0) / vals.length;
    }
    return 0;
  }
  function renderMetrics() {
    const a = cases.before.metrics, b = cases.after.metrics;
    $('metrics').innerHTML = METRICS.map(function (row) {
      const key = row[0], factor = row[2], av = metricValue(a, key) * factor, bv = metricValue(b, key) * factor, delta = bv - av;
      const digits = row[3] === '批' ? 0 : 2;
      const improvement = row[4] === null ? '' : Math.abs(delta) < 1e-9 ? '' : (row[4] ? delta > 0 : delta < 0) ? 'better' : 'worse';
      return '<tr><td>' + row[1] + '</td><td>' + fmt(av, digits) + ' ' + row[3] + '</td><td>' + fmt(bv, digits) + ' ' + row[3] + '</td><td class="' + improvement + '">' + (delta > 0 ? '+' : '') + fmt(delta, digits) + ' ' + row[3] + '</td></tr>';
    }).join('');
    const distance = 100 * (a.loaded_distance_raw - b.loaded_distance_raw) / a.loaded_distance_raw;
    const sojourn = 100 * (a.mean_sojourn_min - b.mean_sojourn_min) / a.mean_sojourn_min;
    $('result-reading').textContent = '本场景载货距离' + (distance >= 0 ? '降低 ' : '增加 ') + fmt(Math.abs(distance), 3) + '%；平均等设备时间 ' + fmt(a.mean_wait_equipment_min) + ' → ' + fmt(b.mean_wait_equipment_min) + ' min / 批，平均区域停留时间' + (sojourn >= 0 ? '降低 ' : '增加 ') + fmt(Math.abs(sojourn), 3) + '%。设备排队可能抵消物流收益。搬运请求时间含等车、空驶接货、装载、载货行驶和卸载。此处为本次整数任务仿真的结果，不套用上周聚合模型的 0.582%。';
  }
  function draw() {
    $('time').value = state.time;
    $('clock').textContent = fmt(state.time) + ' min';
    $('progress-label').textContent = '第 ' + (Math.floor(state.time / 1440) + 1) + ' 天 · ' + fmt(100 * state.time / duration(), 1) + '% 全程';
    renderCase('before'); renderCase('after'); renderTimelinePointer();
  }
  function pause() {
    state.playing = false; lastFrame = null; $('play').textContent = '播放';
    if (frame !== null) { cancelAnimationFrame(frame); frame = null; }
  }
  function tick(now) {
    if (!state.playing) return;
    if (lastFrame !== null) state.time = Math.min(duration(), state.time + Math.min(250, now - lastFrame) / 1000 * state.speed);
    lastFrame = now;
    if (now - lastDraw > 70 || state.time >= duration()) { draw(); lastDraw = now; }
    if (state.time >= duration()) { pause(); return; }
    frame = requestAnimationFrame(tick);
  }
  function play() {
    if (state.playing) return;
    if (state.time >= duration()) state.time = 0;
    state.playing = true; $('play').textContent = '暂停'; lastFrame = null;
    frame = requestAnimationFrame(tick);
  }
  function setTime(time) { const value = Number(time); if (!Number.isFinite(value)) return; state.time = Math.max(0, Math.min(duration(), value)); draw(); }
  function setSpeed(speed) {
    const value = Number(speed);
    if (!(value > 0 && Number.isFinite(value))) throw new Error('Playback speed must be positive');
    state.speed = value; $('speed').value = String(value); return state.speed;
  }
  function selectTask(id) {
    if (!taskMaps.before.has(id) || !taskMaps.after.has(id)) throw new Error('Unknown common task: ' + id);
    state.task = id; $('task').value = id;
    selectedTasks = {before: taskMaps.before.get(id), after: taskMaps.after.get(id)};
    initMaps(); initTimeline(); draw();
  }
  function setScenario(id) {
    if (!DATA.scenarios.some(function (s) { return s.id === id; })) throw new Error('Unknown scenario: ' + id);
    pause(); state.scenario = id; state.time = 0; $('scenario').value = id;
    const s = scenario(); cases = s.cases;
    taskMaps = {before: new Map(cases.before.tasks.map(function (t) { return [t.task_id, t]; })), after: new Map(cases.after.tasks.map(function (t) { return [t.task_id, t]; }))};
    $('task').replaceChildren();
    cases.before.tasks.forEach(function (task) {
      const option = document.createElement('option'); option.value = task.task_id;
      option.textContent = task.task_id + ' · ' + task.part + ' 第 ' + task.step + ' 步'; $('task').append(option);
    });
    const distinct = new Set(cases.before.tasks.map(function (t) { return t.part + ':' + t.step; })).size;
    $('scenario-description').textContent = s.description + ' · ' + distinct + ' 道区域工序 / ' + s.task_count + ' 次工序访问 · ' + s.fleet_size + ' 辆局部情景车。';
    $('time').max = duration();
    const example = cases.before.tasks.find(function (t) { return t.part === 'part_5' && t.step === 169; }) || cases.before.tasks[0];
    selectTask(taskMaps.before.has(state.task) ? state.task : example.task_id);
    renderMetrics();
  }
  function nextStage() {
    pause();
    const times = [];
    ['before', 'after'].forEach(function (name) { selectedTasks[name].timeline.forEach(function (s) { if (s.t0 > state.time + .00001) times.push(s.t0); if (s.t1 > state.time + .00001) times.push(s.t1); }); });
    if (times.length) setTime(Math.min.apply(null, times) + .000001);
  }
  function exportCSV() {
    const rows = [['指标', '参考布局', 'MILP布局', '单位']].concat(METRICS.map(function (row) { return [row[1], metricValue(cases.before.metrics, row[0]) * row[2], metricValue(cases.after.metrics, row[0]) * row[2], row[3]]; }));
    const csv = '\ufeff' + rows.map(function (row) { return row.map(function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; }).join(','); }).join('\r\n');
    const link = document.createElement('a'); const url = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
    link.href = url; link.download = 'a2-a3-' + state.scenario + '-metrics.csv'; link.click(); setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }
  DATA.scenarios.forEach(function (s) { const option = document.createElement('option'); option.value = s.id; option.textContent = s.label; $('scenario').append(option); });
  $('play').addEventListener('click', function () { if (state.playing) pause(); else play(); });
  $('reset').addEventListener('click', function () { pause(); setTime(0); });
  $('jump-end').addEventListener('click', function () { pause(); setTime(duration()); });
  $('speed').addEventListener('change', function (e) { setSpeed(e.target.value); });
  $('scenario').addEventListener('change', function (e) { setScenario(e.target.value); });
  $('task').addEventListener('change', function (e) { selectTask(e.target.value); });
  $('map-view').addEventListener('change', function (e) { setView(e.target.value); });
  $('view-factory').addEventListener('click',function(){setView('factory');});
  $('view-local').addEventListener('click',function(){setView('local');});
  $('zoom-in').addEventListener('click',function(){setZoom(state.zoom*1.5);});
  $('zoom-out').addEventListener('click',function(){setZoom(state.zoom/1.5);});
  $('reset-camera').addEventListener('click',resetCamera);
  $('pan-left').addEventListener('click',function(){panCamera(-1,0);});
  $('pan-right').addEventListener('click',function(){panCamera(1,0);});
  $('pan-up').addEventListener('click',function(){panCamera(0,-1);});
  $('pan-down').addEventListener('click',function(){panCamera(0,1);});
  $('wide-maps').addEventListener('change',function(e){$('map-comparison').classList.toggle('wide-maps',e.target.checked);});
  $('show-other-vehicles').addEventListener('change', function (e) { state.showOtherVehicles = e.target.checked; draw(); });
  $('time').addEventListener('input', function (e) { pause(); setTime(e.target.value); });
  $('locate').addEventListener('click', function () { pause(); setTime(selectedTasks.before.release); });
  $('next-stage').addEventListener('click', nextStage);
  $('download-metrics').addEventListener('click', exportCSV);
  document.addEventListener('visibilitychange', function () { if (document.hidden) pause(); });
  const assumptions = DATA.meta.assumptions || [];
  $('assumptions').innerHTML = assumptions.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('');
  $('verification-note').textContent = '车辆、设备、等待与路径回放均来自事件时间戳。设备加工采用确定性机时折算；速度换算和装卸时长为公开列明的场景假设。';
  window.SimPlayer = {
    play: play, pause: pause, setTime: setTime, setSpeed: setSpeed, selectTask: selectTask, setScenario: setScenario,
    nextStage: nextStage, pointAlong: pointAlong, taskState: taskState, taskPose: taskPose,
    setView:setView,setZoom:setZoom,resetCamera:resetCamera,
    getState: function () { return {scenario: state.scenario, time: state.time, speed: state.speed, playing: state.playing, task: state.task, view: state.view, zoom:state.zoom,cameraX:state.cameraX,cameraY:state.cameraY,showOtherVehicles: state.showOtherVehicles, duration: duration(), taskCount: scenario().task_count, currentBefore: currentData('before').count, currentAfter: currentData('after').count}; }
  };
  setScenario(state.scenario);
  if (typeof ResizeObserver !== 'undefined') {
    let width = $('timelines').clientWidth;
    new ResizeObserver(function () { const next = $('timelines').clientWidth; if (next !== width) { width = next; initTimeline(); renderTimelinePointer(); } }).observe($('timelines'));
  }
}());
