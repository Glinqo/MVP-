/**
 * ForceGraph v3 - Label-optimized force-directed graph
 * Features: collision-avoidance labels, circle-init, no center pull, strong repulsion
 */
class ForceGraph {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) { console.warn("ForceGraph: container", containerId, "not found"); return; }
        this.id = containerId;
        this.options = Object.assign({
            chargeStrength: -850,
            linkDistance: 165,
            alphaDecay: 0.025,
            velocityDecay: 0.42,
            collideExtra: 22,
            minRadius: 28,
            maxRadius: 54
        }, options);
        this._initSize();
        this._setupSVG();
        this._setupSimulation();
        this._setupZoom();
        this.nodes = [];
        this.edges = [];
        this.onNodeClick = options.onNodeClick || null;
    }

    _initSize() {
        let w = this.container.clientWidth;
        let h = this.container.clientHeight;
        if (w === 0 || h === 0) {
            const p = this.container.parentElement;
            if (p) { w = p.clientWidth || 900; h = p.clientHeight || 550; }
            else { w = 900; h = 550; }
        }
        this.width = Math.max(w, 700);
        this.height = Math.max(h, 450);
    }

    _dimColor(dim) {
        const m = {
            root: { fill: '#f8fafc', stroke: '#334155', text: '#0f172a', icon: '\u{1F3AF}' },
            safety: { fill: '#fef2f2', stroke: '#dc2626', text: '#991b1b', icon: '\u26A1' },
            sensor: { fill: '#eff6ff', stroke: '#2563eb', text: '#1e40af', icon: '\u{1F4E1}' },
            plc: { fill: '#ecfdf5', stroke: '#059669', text: '#065f46', icon: '\u2699' },
            fault: { fill: '#f5f3ff', stroke: '#7c3aed', text: '#4c1d95', icon: '\u{1F527}' },
            _: { fill: '#f8fafc', stroke: '#64748b', text: '#1e293b', icon: '\u{1F4A0}' }
        };
        const d = (dim || '').toLowerCase();
        if (d.includes('root') || d.includes('role') || d.includes('student')) return m.root;
        if (d.includes('safety') || d.includes('安全')) return m.safety;
        if (d.includes('sensor') || d.includes('传感')) return m.sensor;
        if (d.includes('plc') || d.includes('控制')) return m.plc;
        if (d.includes('trouble') || d.includes('故障') || d.includes('排故')) return m.fault;
        return m._;
    }

    _statusStyle(status) {
        const m = {
            root: { stroke: '#334155', width: 3, dash: '' },
            weak: { stroke: '#dc2626', width: 3.5, dash: '' },
            mastered: { stroke: '#16a34a', width: 3.5, dash: '' },
            improving: { stroke: '#0891b2', width: 3, dash: '' },
            industry_hot: { stroke: '#d97706', width: 3, dash: '6,4' },
            recommended_next: { stroke: '#ea580c', width: 3, dash: '6,4' },
            core: { stroke: '#059669', width: 2, dash: '' },
            industry: { stroke: '#2563eb', width: 1.5, dash: '5,4' },
            touched: { stroke: '#4f46e5', width: 2, dash: '' },
            _: { stroke: '#94a3b8', width: 1.5, dash: '' }
        };
        return m[status] || m._;
    }

    _edgeEndpointId(value) {
        if (value == null) return null;
        if (typeof value === 'object') return value.id;
        return String(value);
    }

    _virtualNode(id, graphData) {
        const labelMap = {
            role: graphData?.job_role || '岗位能力图谱',
            student: '学生个人能力图谱',
            current: '当前问题图谱'
        };
        return {
            id,
            key: id,
            label: labelMap[id] || graphData?.graph_title || id,
            name: labelMap[id] || graphData?.graph_title || id,
            status: 'root',
            status_label: '中心',
            radar_dimension_ids: ['root'],
            source: 'graph_anchor',
            is_virtual: true
        };
    }

    _labelLines(text, maxChars = 9, maxLines = 3) {
        const value = String(text || '');
        const lines = [];
        for (let i = 0; i < value.length; i += maxChars) {
            lines.push(value.slice(i, i + maxChars));
        }
        if (lines.length > maxLines) {
            const trimmed = lines.slice(0, maxLines);
            trimmed[maxLines - 1] = `${trimmed[maxLines - 1].slice(0, Math.max(1, maxChars - 2))}..`;
            return trimmed;
        }
        return lines.length ? lines : [''];
    }

    _nodeRadius(node) {
        if (node.status === 'root') return 48;
        const degreeBonus = Math.min(14, (node.degree || 0) * 3);
        const demandBonus = Math.min(12, (node.demand_weight || 0) * 6);
        const evidenceBonus = Math.min(8, (node.evidence_count || 0) * 1.5);
        return Math.max(
            this.options.minRadius,
            Math.min(this.options.maxRadius, this.options.minRadius + degreeBonus + demandBonus + evidenceBonus)
        );
    }

    _keepInBounds(node) {
        const pad = (node.radius || 32) + 68;
        node.x = Math.max(pad, Math.min(this.width - pad, node.x || this.width / 2));
        node.y = Math.max(pad, Math.min(this.height - pad, node.y || this.height / 2));
    }

    _setupSVG() {
        this.svg = d3.select(this.container)
            .append('svg').attr('width', this.width).attr('height', this.height)
            .attr('viewBox', [0, 0, this.width, this.height])
            .style('background', '#ffffff')
            .style('border-radius', '8px')
            .style('cursor', 'grab');
        this.defs = this.svg.append('defs');

        // Node drop shadow
        const f = this.defs.append('filter').attr('id', 'ns').attr('x', '-30%').attr('y', '-30%').attr('width', '160%').attr('height', '160%');
        f.append('feDropShadow').attr('dx', 0).attr('dy', 2).attr('stdDeviation', 3).attr('flood-opacity', 0.12);

        // Arrow marker
        this.defs.append('marker').attr('id', 'ar').attr('viewBox', '0 -5 10 10').attr('refX', 38).attr('refY', 0).attr('markerWidth', 5).attr('markerHeight', 5).attr('orient', 'auto')
            .append('path').attr('d', 'M0,-4L8,0L0,4').attr('fill', '#94a3b8');

        // Grid background
        const g = this.defs.append('pattern').attr('id', 'gd').attr('width', 24).attr('height', 24).attr('patternUnits', 'userSpaceOnUse');
        g.append('path').attr('d', 'M 24 0 L 0 0 0 24').attr('fill', 'none').attr('stroke', '#f1f5f9').attr('stroke-width', 0.5);
        this.svg.append('rect').attr('width', '100%').attr('height', '100%').attr('fill', 'url(#gd)');

        this.linkG = this.svg.append('g');
        this.nodeG = this.svg.append('g');
        this.labelG = this.svg.append('g');
        this.legendG = this.svg.append('g').attr('class', 'graph-legend');
    }

    _setupSimulation() {
        this.sim = d3.forceSimulation()
            .force('link', d3.forceLink().id(d => d.id).distance(this.options.linkDistance))
            .force('charge', d3.forceManyBody().strength(this.options.chargeStrength))
            .force('center', d3.forceCenter(this.width / 2, this.height / 2).strength(0.05))
            .force('collide', d3.forceCollide(d => (d.radius || 32) + this.options.collideExtra))
            .alphaDecay(this.options.alphaDecay)
            .velocityDecay(this.options.velocityDecay);
    }

    _setupZoom() {
        const z = d3.zoom().scaleExtent([0.2, 4]).on('zoom', ev => {
            this.linkG.attr('transform', ev.transform);
            this.nodeG.attr('transform', ev.transform);
            this.labelG.attr('transform', ev.transform);
        });
        this.svg.call(z);
    }

    _drag() {
        const s = this.sim;
        return d3.drag()
            .on('start', (ev) => { if (!ev.active) s.alphaTarget(0.3).restart(); ev.subject.fx = ev.subject.x; ev.subject.fy = ev.subject.y; })
            .on('drag', (ev) => { ev.subject.fx = ev.x; ev.subject.fy = ev.y; })
            .on('end', (ev) => { if (!ev.active) s.alphaTarget(0); if (!ev.subject._pin) { ev.subject.fx = null; ev.subject.fy = null; } });
    }

    _circleInit(nodes) {
        const r = Math.min(this.width, this.height) * 0.35;
        const cx = this.width / 2, cy = this.height / 2;
        nodes.forEach((n, i) => {
            const a = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
            n.x = cx + r * Math.cos(a);
            n.y = cy + r * Math.sin(a);
        });
    }

    _statusLegendItems(nodes) {
        const present = new Set((nodes || []).map(node => node.status));
        const all = [
            { status: 'industry_hot', label: '行业高频' },
            { status: 'core', label: '岗位核心' },
            { status: 'industry', label: '行业补充' },
            { status: 'weak', label: '薄弱' },
            { status: 'improving', label: '正在提升' },
            { status: 'mastered', label: '已掌握' },
            { status: 'recommended_next', label: '建议下一步' },
            { status: 'touched', label: '问答命中' },
            { status: 'root', label: '中心节点' },
        ];
        const visible = all.filter(item => present.has(item.status));
        return visible.length ? visible.slice(0, 5) : all.slice(0, 3);
    }

    _renderLegend(graphData, nodes, edges) {
        const g = this.legendG;
        g.selectAll('*').remove();

        const width = this.width < 920 ? 246 : 292;
        const x = Math.max(14, this.width - width - 18);
        const y = 16;
        const dimensionItems = [
            { key: 'electrical_safety_diagram', label: '电气安全' },
            { key: 'sensor_signal_acquisition', label: '传感器/信号' },
            { key: 'plc_control_debug', label: 'PLC 控制' },
            { key: 'equipment_inspection_troubleshooting', label: '排故诊断' },
        ].map(item => ({ ...item, color: this._dimColor(item.key) }));
        const statusItems = this._statusLegendItems(nodes);
        const height = 246 + statusItems.length * 22;

        g.attr('transform', `translate(${x},${y})`);
        g.append('rect')
            .attr('width', width)
            .attr('height', height)
            .attr('rx', 12)
            .attr('ry', 12)
            .attr('fill', 'rgba(255,255,255,0.94)')
            .attr('stroke', '#cbd5e1')
            .attr('stroke-width', 1)
            .attr('filter', 'url(#ns)');

        g.append('text')
            .attr('x', 14)
            .attr('y', 24)
            .attr('font-size', 13)
            .attr('font-weight', 800)
            .attr('fill', '#0f172a')
            .text('图例 · 读图规则');

        g.append('text')
            .attr('x', 14)
            .attr('y', 43)
            .attr('font-size', 10.5)
            .attr('fill', '#64748b')
            .text('参考网络图：颜色分社区，大小看连接强度');

        let cy = 67;
        g.append('text').attr('x', 14).attr('y', cy).attr('font-size', 11).attr('font-weight', 700).attr('fill', '#334155').text('颜色 = 能力维度/社区');
        cy += 15;
        dimensionItems.forEach((item, index) => {
            const rowY = cy + index * 21;
            g.append('circle')
                .attr('cx', 22)
                .attr('cy', rowY)
                .attr('r', 6)
                .attr('fill', item.color.fill)
                .attr('stroke', item.color.stroke)
                .attr('stroke-width', 1.4);
            g.append('text')
                .attr('x', 36)
                .attr('y', rowY + 4)
                .attr('font-size', 11)
                .attr('fill', '#1e293b')
                .text(item.label);
        });

        cy += dimensionItems.length * 21 + 12;
        g.append('text').attr('x', 14).attr('y', cy).attr('font-size', 11).attr('font-weight', 700).attr('fill', '#334155').text('大小 = 连接度/证据强度');
        const sizeY = cy + 23;
        [
            { r: 5, label: '低' },
            { r: 8, label: '中' },
            { r: 12, label: '高' },
        ].forEach((item, index) => {
            const cx = 28 + index * 58;
            g.append('circle')
                .attr('cx', cx)
                .attr('cy', sizeY)
                .attr('r', item.r)
                .attr('fill', '#f8fafc')
                .attr('stroke', '#64748b')
                .attr('stroke-width', 1.2);
            g.append('text')
                .attr('x', cx + 16)
                .attr('y', sizeY + 4)
                .attr('font-size', 10.5)
                .attr('fill', '#475569')
                .text(item.label);
        });

        cy += 54;
        g.append('text').attr('x', 14).attr('y', cy).attr('font-size', 11).attr('font-weight', 700).attr('fill', '#334155').text('线条 = 关系类型');
        const edgeY1 = cy + 19;
        g.append('line').attr('x1', 18).attr('y1', edgeY1).attr('x2', 56).attr('y2', edgeY1).attr('stroke', '#cbd5e1').attr('stroke-width', 2).attr('marker-end', 'url(#ar)');
        g.append('text').attr('x', 68).attr('y', edgeY1 + 4).attr('font-size', 10.5).attr('fill', '#475569').text('主链/先后依赖');
        const edgeY2 = edgeY1 + 22;
        g.append('line').attr('x1', 18).attr('y1', edgeY2).attr('x2', 56).attr('y2', edgeY2).attr('stroke', '#94a3b8').attr('stroke-width', 1.5).attr('stroke-dasharray', '6,4').attr('marker-end', 'url(#ar)');
        g.append('text').attr('x', 68).attr('y', edgeY2 + 4).attr('font-size', 10.5).attr('fill', '#475569').text('行业/证据补充');

        cy += 66;
        g.append('text').attr('x', 14).attr('y', cy).attr('font-size', 11).attr('font-weight', 700).attr('fill', '#334155').text('外环 = 节点状态');
        cy += 19;
        statusItems.forEach((item, index) => {
            const rowY = cy + index * 22;
            const style = this._statusStyle(item.status);
            g.append('circle')
                .attr('cx', 24)
                .attr('cy', rowY - 3)
                .attr('r', 8)
                .attr('fill', '#ffffff')
                .attr('stroke', style.stroke)
                .attr('stroke-width', Math.max(1.6, Math.min(3, style.width)))
                .attr('stroke-dasharray', style.dash);
            g.append('text')
                .attr('x', 42)
                .attr('y', rowY + 1)
                .attr('font-size', 10.5)
                .attr('fill', '#475569')
                .text(item.label);
        });

        const hintY = height - 15;
        g.append('text')
            .attr('x', 14)
            .attr('y', hintY)
            .attr('font-size', 10.5)
            .attr('fill', '#64748b')
            .text('滚轮缩放 · 拖拽节点 · 点击查看证据');
    }

    update(graphData) {
        if (!graphData || !graphData.nodes) return;
        const nodeMap = new Map();
        (graphData.nodes || []).forEach(n => {
            const id = this._edgeEndpointId(n.id || n.key);
            if (!id) return;
            nodeMap.set(id, { ...n, id, name: n.label || n.name || id });
        });
        const edges = (graphData.edges || []).map(e => ({
            source: this._edgeEndpointId(e.from || e.source),
            target: this._edgeEndpointId(e.to || e.target),
            type: e.type || 'default'
        })).filter(e => e.source && e.target);

        edges.forEach(edge => {
            if (!nodeMap.has(edge.source)) nodeMap.set(edge.source, this._virtualNode(edge.source, graphData));
            if (!nodeMap.has(edge.target)) nodeMap.set(edge.target, this._virtualNode(edge.target, graphData));
        });

        const degree = new Map();
        edges.forEach(edge => {
            degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
            degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
        });

        const nodes = Array.from(nodeMap.values()).map(n => {
            const labelLines = this._labelLines(n.name);
            return {
                ...n,
                degree: degree.get(n.id) || 0,
                labelLines,
                labelWidth: Math.max(...labelLines.map(line => line.length), 3) * 11 + 16,
                labelHeight: labelLines.length * 15 + 8
            };
        }).map(n => ({ ...n, radius: this._nodeRadius(n), labelDx: 0, labelDy: 0 }));
        this._circleInit(nodes);

        // --- EDGES ---
        this.linkG.selectAll('line').remove();
        this.selEdges = this.linkG.selectAll('line').data(edges, d => d.source + '-' + d.target)
            .enter().append('line')
            .attr('stroke', d => d.type === 'industry_extension' ? '#94a3b8' : '#cbd5e1')
            .attr('stroke-width', d => d.type === 'industry_extension' ? 1 : 2)
            .attr('stroke-dasharray', d => d.type === 'industry_extension' ? '6,4' : null)
            .attr('marker-end', 'url(#ar)').attr('opacity', 0.45);

        // --- NODES ---
        this.nodeG.selectAll('g').remove();
        const ng = this.nodeG.selectAll('g').data(nodes, d => d.id).enter().append('g').attr('class', 'node').call(this._drag());

        // Status ring
        ng.append('circle').attr('class', 'sr')
            .attr('r', d => d.radius + 5)
            .attr('fill', 'none')
            .attr('stroke', d => this._statusStyle(d.status).stroke)
            .attr('stroke-width', d => this._statusStyle(d.status).width)
            .attr('stroke-dasharray', d => this._statusStyle(d.status).dash)
            .style('cursor', 'pointer');

        // Inner fill
        ng.append('circle').attr('class', 'nf')
            .attr('r', d => d.radius)
            .attr('fill', d => this._dimColor(d.radar_dimension_ids?.[0] || '').fill)
            .attr('stroke', d => this._dimColor(d.radar_dimension_ids?.[0] || '').stroke)
            .attr('stroke-width', 1.5)
            .attr('filter', 'url(#ns)')
            .style('cursor', 'pointer');

        // Icon
        ng.append('text').attr('text-anchor', 'middle').attr('dy', 4).attr('font-size', '20px').attr('pointer-events', 'none')
            .text(d => this._dimColor(d.radar_dimension_ids?.[0] || '').icon);

        // Status label
        const sb = { root: '中', weak: '弱', mastered: '掌', improving: '升', industry_hot: '热', recommended_next: '荐', core: '核', industry: '补', touched: '问', unknown: '?' };
        ng.append('text').attr('text-anchor', 'middle').attr('dy', d => d.radius + 4).attr('font-size', '9px').attr('font-weight', '700')
            .attr('fill', d => this._dimColor(d.radar_dimension_ids?.[0] || '').text)
            .attr('pointer-events', 'none')
            .text(d => sb[d.status] || '·');

        this.selNodes = ng;

        // --- LABELS ---
        this.labelG.selectAll('g').remove();
        const lg = this.labelG.selectAll('g').data(nodes, d => d.id).enter().append('g');

        // Label background (hidden, sized by text)
        lg.append('rect').attr('class', 'lb').attr('rx', 4).attr('ry', 4)
            .attr('fill', 'rgba(255,255,255,0.92)').attr('stroke', '#e2e8f0').attr('stroke-width', 1);

        // Label text
        const labelText = lg.append('text').attr('class', 'lt').attr('text-anchor', 'middle').attr('font-size', '11px').attr('font-weight', '600')
            .attr('fill', '#1e293b').attr('pointer-events', 'none');
        labelText.each(function(d) {
            const text = d3.select(this);
            d.labelLines.forEach((line, index) => {
                text.append('tspan')
                    .attr('x', 0)
                    .attr('dy', index === 0 ? 0 : 14)
                    .text(line);
            });
        });

        // Resize label backgrounds using estimated size (avoids getBBox issue in hidden containers)
        lg.each(function(d) {
            const t = d3.select(this).select('.lt');
            const b = d3.select(this).select('.lb');
            const estW = d.labelWidth;
            const estH = d.labelHeight;
            t.attr('dy', d.labelLines.length === 1 ? 4 : -((d.labelLines.length - 1) * 7) + 4);
            b.attr('x', -estW/2).attr('y', -estH/2 - 1).attr('width', estW).attr('height', estH);
        });

        this.selLabels = lg;
        this._renderLegend(graphData, nodes, edges);

        // Click
        if (this.onNodeClick) {
            ng.on('click', (ev, d) => { ev.stopPropagation(); this.onNodeClick(d, graphData); });
        }

        // Run simulation
        this.nodes = nodes; this.edges = edges;
        this.sim.nodes(nodes);
        this.sim.force('link').links(edges);
        this.sim.alpha(0.8).restart();

        // Tick: update positions + label overlap resolution
        this.sim.on('tick', () => {
            this.nodes.forEach(d => this._keepInBounds(d));
            this.selEdges
                .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
            this.selNodes.attr('transform', d => `translate(${d.x},${d.y})`);
            this.selLabels.attr('transform', d => `translate(${(d.x || 0) + (d.labelDx || 0)},${(d.y || 0) + (d.radius || 32) + 22 + (d.labelDy || 0)})`);

            // Label collision avoidance
            this._resolveLabelOverlaps();
        });
    }

    _resolveLabelOverlaps() {
        const els = this.selLabels.nodes();
        if (!els.length) return;
        const boxes = [];
        for (let i = 0; i < els.length; i++) {
            const el = els[i];
            const d = d3.select(el).datum();
            if (!d) continue;
            const t = el.getAttribute('transform');
            const m = t?.match(/translate\(([\d.-]+),([\d.-]+)\)/);
            if (!m) continue;
            const gx = parseFloat(m[1]), gy = parseFloat(m[2]);
            const labelW = d.labelWidth || 96;
            const labelH = d.labelHeight || 22;
            boxes.push({
                l: gx - labelW / 2, r: gx + labelW / 2,
                t: gy - labelH / 2, b: gy + labelH / 2,
                cx: gx,
                cy: gy,
                w: labelW, h: labelH,
                idx: i
            });
        }
        for (let i = 0; i < boxes.length; i++) {
            for (let j = i + 1; j < boxes.length; j++) {
                const a = boxes[i], b = boxes[j];
                const ox = Math.min(a.r, b.r) - Math.max(a.l, b.l);
                const oy = Math.min(a.b, b.b) - Math.max(a.t, b.t);
                if (ox > 0 && oy > 0) {
                    const dx = b.cx - a.cx, dy = b.cy - a.cy;
                    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                    const push = Math.min(ox, oy) * 0.18 + 1;
                    const nx = dx / dist * push, ny = dy / dist * push;
                    const ni = this.nodes[a.idx], nj = this.nodes[b.idx];
                    if (ni && nj) {
                        ni.labelDx = Math.max(-70, Math.min(70, (ni.labelDx || 0) - nx));
                        ni.labelDy = Math.max(-40, Math.min(55, (ni.labelDy || 0) - ny));
                        nj.labelDx = Math.max(-70, Math.min(70, (nj.labelDx || 0) + nx));
                        nj.labelDy = Math.max(-40, Math.min(55, (nj.labelDy || 0) + ny));
                    }
                }
            }
        }
        this.selLabels.attr('transform', d => `translate(${(d.x || 0) + (d.labelDx || 0)},${(d.y || 0) + (d.radius || 32) + 22 + (d.labelDy || 0)})`);
    }

    resize() {
        this._initSize();
        this.svg.attr('width', this.width).attr('height', this.height).attr('viewBox', [0, 0, this.width, this.height]);
        this.sim.force('center', d3.forceCenter(this.width / 2, this.height / 2).strength(0.05));
        this.sim.alpha(0.5).restart();
    }

    destroy() { this.sim?.stop(); this.svg?.remove(); }
}
