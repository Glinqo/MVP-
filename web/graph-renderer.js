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
            chargeStrength: -1200,
            linkDistance: 200,
            alphaDecay: 0.018,
            velocityDecay: 0.38,
            collideExtra: 28,
            minRadius: 24,
            maxRadius: 60
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
            root: { fill: '#1e293b', stroke: '#475569', text: '#cbd5e1', icon: '\u{1F3AF}' },
            safety: { fill: 'rgba(239,68,68,0.18)', stroke: '#ef4444', text: '#fca5a5', icon: '\u26A1' },
            sensor: { fill: 'rgba(59,130,246,0.18)', stroke: '#60a5fa', text: '#93c5fd', icon: '\u{1F4E1}' },
            plc: { fill: 'rgba(5,150,105,0.18)', stroke: '#34d399', text: '#6ee7b7', icon: '\u2699' },
            fault: { fill: 'rgba(124,58,237,0.18)', stroke: '#a78bfa', text: '#a78bfa', icon: '\u{1F527}' },
            _: { fill: '#1e293b', stroke: '#64748b', text: '#94a3b8', icon: '\u{1F4A0}' }
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
        const pad = (node.radius || 32) + 15;
       node.x = Math.max(pad, Math.min(this.width - pad, node.x || this.width / 2));
       node.y = Math.max(pad, Math.min(this.height - pad, node.y || this.height / 2));
   }

    _setupSVG() {
        this.svg = d3.select(this.container)
            .append('svg').attr('width', this.width).attr('height', this.height)
            .attr('viewBox', [0, 0, this.width, this.height])
            .style('background', '#0a1628')
            .style('border-radius', '8px')
            .style('cursor', 'grab');
        this.defs = this.svg.append('defs');

        // Node drop shadow
        const f = this.defs.append('filter').attr('id', 'ns').attr('x', '-30%').attr('y', '-30%').attr('width', '160%').attr('height', '160%');
        f.append('feDropShadow').attr('dx', 0).attr('dy', 2).attr('stdDeviation', 3).attr('flood-opacity', 0.12);

        // Arrow marker
        this.defs.append('marker').attr('id', 'ar').attr('viewBox', '0 -5 10 10').attr('refX', 38).attr('refY', 0).attr('markerWidth', 5).attr('markerHeight', 5).attr('orient', 'auto')
            .append('path').attr('d', 'M0,-4L8,0L0,4').attr('fill', '#475569');

        // Grid background
        const g = this.defs.append('pattern').attr('id', 'gd').attr('width', 32).attr('height', 32).attr('patternUnits', 'userSpaceOnUse');
        g.append('path').attr('d', 'M 24 0 L 0 0 0 24').attr('fill', 'none').attr('stroke', '#1e293b').attr('stroke-width', 0.5);
        this.svg.append('rect').attr('width', '100%').attr('height', '100%').attr('fill', 'url(#gd)');

        this.linkG = this.svg.append('g');
        this.nodeG = this.svg.append('g');
        this.labelG = this.svg.append('g');
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
    }    update(graphData) {
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

        // --- EDGES (curved paths) ---
        this.linkG.selectAll('path').remove();
        this.selEdges = this.linkG.selectAll('path').data(edges, d => d.source + '-' + d.target)
            .enter().append('path')
            .attr('fill', 'none')
            .attr('stroke', d => {
                if (d.type === 'hierarchy') return '#475569';
                if (d.type === 'industry_extension') return '#4b5563';
                return '#64748b';
            })
            .attr('stroke-width', d => {
                if (d.type === 'hierarchy') return 0.8;
                if (d.type === 'industry_extension') return 1;
                return 1.8;
            })
            .attr('stroke-dasharray', d => (d.type === 'industry_extension' || d.type === 'hierarchy') ? '4,4' : null)
            .attr('marker-end', d => (d.type === 'industry_extension' || d.type === 'hierarchy') ? null : 'url(#ar)')
            .attr('opacity', d => d.type === 'hierarchy' ? 0.3 : 0.5);

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

        // Inner fill - gradient-like with glow
        ng.append('circle').attr('class', 'ng')
            .attr('r', d => d.radius + 3)
            .attr('fill', 'none')
            .attr('stroke', d => this._dimColor(d.radar_dimension_ids?.[0] || '').stroke)
            .attr('stroke-width', 0.5)
            .attr('opacity', 0.3);
        ng.append('circle').attr('class', 'nf')
            .attr('r', d => d.radius)
            .attr('fill', d => this._dimColor(d.radar_dimension_ids?.[0] || '').fill)
            .attr('stroke', d => this._dimColor(d.radar_dimension_ids?.[0] || '').stroke)
            .attr('stroke-width', 1.2)
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
            .attr('fill', 'rgba(15,29,53,0.92)').attr('stroke', '#334155').attr('stroke-width', 1);

        // Label text
        const labelText = lg.append('text').attr('class', 'lt').attr('text-anchor', 'middle').attr('font-size', '11px').attr('font-weight', '600')
            .attr('fill', '#e2e8f0').attr('pointer-events', 'none');
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
                .attr('d', d => {
                    const sx = d.source.x, sy = d.source.y;
                    const tx = d.target.x, ty = d.target.y;
                    const dx = tx - sx, dy = ty - sy;
                    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                    const curve = Math.min(dist * 0.15, 40);
                    const mx = (sx + tx) / 2 - (dy / dist) * curve;
                    const my = (sy + ty) / 2 + (dx / dist) * curve;
                    return `M${sx},${sy} Q${mx},${my} ${tx},${ty}`;
                });
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
