/* The home-page structure viewer.
 *
 * Rules this file exists to honour:
 *  - It must never block first paint. 3Dmol.js is ~525 KB and is not requested
 *    at all until the visitor asks for it, or until the poster scrolls into
 *    view on a connection that looks willing.
 *  - prefers-reduced-motion means the structure does not spin. It stays
 *    draggable, because that is interaction, not motion inflicted on a reader.
 *  - If anything fails -- no network, blocked CDN, WebGL unavailable -- the
 *    poster image stays and the page is not broken. The viewer is an
 *    enhancement, never a dependency.
 */
(function () {
  'use strict';

  var CDN = 'https://cdn.jsdelivr.net/npm/3dmol@2.5.5/build/3Dmol-min.js';
  var INTEGRITY = 'sha384-OsczYbldvrHgslr9fFp/i4GiLSeuw9l+QIlv99ITw8soOwXcoGeflFMLg+CU/X1d';
  var SPIN_SPEED = 0.6;           // ~4 s per turn at 3Dmol's default frame rate
  var LIGAND = 'SHH';             // SAHA / vorinostat, as deposited in 4LXZ

  // These must match assets/img/hero-hdac2-4lxz.png, which is rendered from the
  // same values -- otherwise the poster and the live view are visibly different
  // pictures and swapping one for the other looks like a fault.
  var RAMP = ['#6E9A85', '#8CAA93', '#AEB79E', '#CDB49B', '#E09A7E', '#E2664B'];
  var LIGAND_COLOR = '#C2341A';
  var ZINC_COLOR = '#B8862B';

  function rampColor(t) {
    var x = Math.max(0, Math.min(1, t)) * (RAMP.length - 1);
    var i = Math.floor(x), f = x - i;
    var a = RAMP[i], b = RAMP[Math.min(i + 1, RAMP.length - 1)];
    var hx = function (h) {
      return [parseInt(h.substr(1, 2), 16), parseInt(h.substr(3, 2), 16),
              parseInt(h.substr(5, 2), 16)];
    };
    var c1 = hx(a), c2 = hx(b);
    var m = function (u, v) { return Math.round(u + (v - u) * f); };
    return (m(c1[0], c2[0]) << 16) | (m(c1[1], c2[1]) << 8) | m(c1[2], c2[2]);
  }

  var host = document.getElementById('structure-hero');
  if (!host) return;

  var slot = host.querySelector('.hero-figure-slot');
  var button = host.querySelector('.structure-load');
  var status = host.querySelector('.structure-status');
  var pdbPath = host.getAttribute('data-structure');
  var loading = false;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');

  function say(msg) { if (status) status.textContent = msg; }

  // 3Dmol throws deep inside its renderer when there is no WebGL context, after
  // the download has already happened. Ask the cheap question first.
  function webglAvailable() {
    try {
      var probe = document.createElement('canvas');
      return !!(probe.getContext('webgl2') || probe.getContext('webgl')
                || probe.getContext('experimental-webgl'));
    } catch (e) {
      return false;
    }
  }

  function describe(err) {
    if (!err) return 'unknown error';
    return err.message || String(err);
  }

  function loadScript() {
    return new Promise(function (resolve, reject) {
      if (window.$3Dmol) { resolve(); return; }
      var s = document.createElement('script');
      s.src = CDN;
      s.integrity = INTEGRITY;
      s.crossOrigin = 'anonymous';
      s.onload = resolve;
      s.onerror = function () { reject(new Error('3Dmol could not be loaded')); };
      document.head.appendChild(s);
    });
  }

  function fetchStructure() {
    return fetch(pdbPath).then(function (r) {
      if (!r.ok) throw new Error('structure file ' + r.status);
      return r.text();
    });
  }

  function render(pdbText) {
    // Added alongside the poster, never instead of it. If anything below throws,
    // the poster is still on the page and the visitor sees the structure anyway.
    var mount = document.createElement('div');
    mount.className = 'structure-canvas';
    slot.appendChild(mount);

    var viewer = window.$3Dmol.createViewer(mount, {
      backgroundColor: '#FFF8F3',
      antialias: true
    });
    var model = viewer.addModel(pdbText, 'pdb');

    // Sage through sand to coral along the chain: gives the fold depth without
    // the rainbow that makes every structure figure look like every other one.
    var resis = model.selectedAtoms({}).filter(function (a) { return !a.hetflag; })
                     .map(function (a) { return a.resi; });
    var lo = Math.min.apply(null, resis), hi = Math.max.apply(null, resis);
    var span = (hi - lo) || 1;

    viewer.setStyle({}, { cartoon: {
      colorfunc: function (a) { return rampColor((a.resi - lo) / span); },
      thickness: 0.38, arrows: true
    } });
    // The inhibitor and the catalytic zinc -- the two things a visitor should
    // actually be able to pick out.
    viewer.setStyle({ resn: LIGAND }, { stick: { radius: 0.30, color: LIGAND_COLOR } });
    viewer.addStyle({ resn: LIGAND }, { sphere: { radius: 0.38, color: LIGAND_COLOR } });
    viewer.setStyle({ resn: 'ZN' }, { sphere: { radius: 1.05, color: ZINC_COLOR } });

    // Frame the whole domain, matching the poster. Zooming to the ligand and
    // back out put the protein half outside the box.
    viewer.zoomTo();
    viewer.zoom(1.42);
    viewer.render();

    if (!reduce.matches) viewer.spin('y', SPIN_SPEED);

    // Honour a mid-session change of the setting, both directions.
    var onChange = function () {
      if (reduce.matches) viewer.spin(false);
      else viewer.spin('y', SPIN_SPEED);
    };
    if (reduce.addEventListener) reduce.addEventListener('change', onChange);

    host.classList.add('is-live');
    say('HDAC2 with vorinostat bound. Drag to rotate, scroll to zoom.');
    return viewer;
  }

  function activate() {
    if (loading || host.classList.contains('is-live')) return;
    if (!webglAvailable()) {
      host.classList.add('is-failed');
      say('This browser has WebGL unavailable, so the interactive view cannot run. '
          + 'The image is a render of the same structure.');
      return;
    }
    loading = true;
    host.classList.add('is-loading');
    say('Loading the structure…');

    Promise.all([loadScript(), fetchStructure()])
      .then(function (r) { render(r[1]); })
      .catch(function (err) {
        host.classList.remove('is-loading');
        host.classList.add('is-failed');
        loading = false;
        var dead = slot.querySelector('.structure-canvas');
        if (dead) dead.remove();
        // The poster is still there; say why the live view is not.
        say('The interactive view could not load (' + describe(err) + '). '
            + 'The image below is a render of the same structure.');
      })
      .finally(function () { host.classList.remove('is-loading'); });
  }

  if (button) button.addEventListener('click', activate);

  // Auto-load only when the poster is actually on screen and the connection is
  // not metered or slow. Otherwise it waits for a deliberate click.
  var conn = navigator.connection || {};
  var thrifty = conn.saveData === true || /2g/.test(conn.effectiveType || '');
  if ('IntersectionObserver' in window && !thrifty) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { io.disconnect(); activate(); }
      });
    }, { rootMargin: '200px' });
    io.observe(host);
  }
})();
