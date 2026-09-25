/*
 * Motion for the home page. Four jobs, all optional:
 *
 *   1. the scroll cue under the hero, which retires once the visitor scrolls;
 *   2. a one-shot reveal for the two structural blocks (the loop, the routes);
 *   3. the return arrow under the loop, whose path is generated at the
 *      element's own pixel size and then drawn once;
 *   4. the photo reel, which only downloads and plays while it is on screen.
 *
 * Nothing here is load-bearing. With JavaScript off the page is complete and
 * static: the reveal targets are visible by default and only become hidden once
 * this file adds `motion` to <html>, the reel falls back to its poster, and the
 * arrow is simply absent.
 *
 * prefers-reduced-motion is honoured by NOT starting anything — the reveals are
 * shown immediately, the arrow is drawn in its final state, and the reel never
 * plays. The blanket transition-killing rule in styles.scss cannot cover these,
 * because a paused video and an undrawn path are states, not transitions.
 */
(function () {
  'use strict';

  var root = document.documentElement;
  var reduced = window.matchMedia &&
                window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var canObserve = 'IntersectionObserver' in window;

  // Opt the page into the hidden-until-revealed styles. Done here rather than in
  // the stylesheet so that a visitor without JS never meets a blank section.
  root.classList.add('motion');

  // ── 1. Scroll cue ─────────────────────────────────────────────────────────
  var cue = document.querySelector('.scroll-cue');
  if (cue) {
    var retire = function () {
      if (window.scrollY > 120) {
        cue.classList.add('is-gone');
        window.removeEventListener('scroll', retire);
      }
    };
    window.addEventListener('scroll', retire, { passive: true });
    retire();
  }

  // ── 2. Reveals ────────────────────────────────────────────────────────────
  var reveals = [].slice.call(document.querySelectorAll('.reveal'));

  function show(el) {
    el.classList.add('is-in');
    if (el.classList.contains('loop')) drawReturn(el);
  }

  if (!canObserve || reduced) {
    // After a frame, not now: this file is deferred, so it can run before the
    // first layout, and the return arrow is generated from the element's own
    // measured width. Calling show() immediately measured zero and drew nothing.
    requestAnimationFrame(function () { reveals.forEach(show); });
  } else {
    var revealObserver = new IntersectionObserver(function (entries, obs) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        show(entry.target);
        obs.unobserve(entry.target);          // once, not every time it passes
      });
    }, { rootMargin: '0px 0px -12% 0px', threshold: 0.15 });
    reveals.forEach(function (el) { revealObserver.observe(el); });
  }

  // ── 3. The return arrow ───────────────────────────────────────────────────
  // Generated rather than authored so the viewBox matches the element's real
  // pixel size: a stretched viewBox would skew the corner radii and the
  // arrowhead, which is the whole reason the path is not in the markup.
  var NS = 'http://www.w3.org/2000/svg';
  var INSET = 30, RADIUS = 22;

  function buildReturn(svg) {
    var w = Math.round(svg.clientWidth);
    var h = Math.round(svg.clientHeight);
    if (w < 2 * (INSET + RADIUS) + 40 || h < 30) return null;

    var x1 = w - INSET, x0 = INSET, yb = h - 1;
    var d = 'M ' + x1 + ' 0' +
            ' L ' + x1 + ' ' + (yb - RADIUS) +
            ' A ' + RADIUS + ' ' + RADIUS + ' 0 0 1 ' + (x1 - RADIUS) + ' ' + yb +
            ' L ' + (x0 + RADIUS) + ' ' + yb +
            ' A ' + RADIUS + ' ' + RADIUS + ' 0 0 1 ' + x0 + ' ' + (yb - RADIUS) +
            ' L ' + x0 + ' 11';

    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    svg.innerHTML = '';

    var line = document.createElementNS(NS, 'path');
    line.setAttribute('d', d);
    line.setAttribute('class', 'loop-return-line');
    svg.appendChild(line);

    var head = document.createElementNS(NS, 'path');
    head.setAttribute('d', 'M ' + (x0 - 7) + ' 18 L ' + x0 + ' 8 L ' + (x0 + 7) + ' 18');
    head.setAttribute('class', 'loop-return-head');
    svg.appendChild(head);

    return line;
  }

  function drawReturn(loop, retried) {
    var svg = loop.querySelector('.loop-return-path');
    if (!svg) return;
    var line = buildReturn(svg);
    if (!line) {
      // Almost always an unlaid-out element rather than a genuinely narrow one.
      // Below the stacking breakpoint the SVG is display:none and stays absent,
      // which is correct: a horizontal return path under a vertical stack is
      // not a return path.
      if (!retried) requestAnimationFrame(function () { drawReturn(loop, true); });
      return;
    }
    var len = line.getTotalLength();
    line.style.strokeDasharray = len;
    line.style.strokeDashoffset = reduced ? 0 : len;
    if (reduced) { svg.classList.add('is-drawn'); return; }
    // Two frames: one for the dash to take effect, one for the transition to
    // have something to animate from.
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        line.style.strokeDashoffset = 0;
        svg.classList.add('is-drawn');
      });
    });
  }

  var resizeTimer;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      document.querySelectorAll('.loop.is-in .loop-return-path').forEach(function (svg) {
        var line = buildReturn(svg);
        if (!line) return;
        // Already seen: redraw it finished rather than replaying the animation.
        line.style.strokeDasharray = 'none';
        line.style.strokeDashoffset = 0;
        svg.classList.add('is-drawn');
      });
    }, 180);
  }, { passive: true });

  // ── 4. The reel ───────────────────────────────────────────────────────────
  // preload="none" in the markup means the 1.8 MB file is not fetched until the
  // band is actually approached, and never at all under reduced motion.
  var reel = document.querySelector('.reel-video');
  if (reel && !reduced && canObserve) {
    var reelObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          var playing = reel.play();
          if (playing && playing.catch) playing.catch(function () { /* poster stands */ });
        } else if (!reel.paused) {
          reel.pause();
        }
      });
    }, { threshold: 0.35 });
    reelObserver.observe(reel);
  }
})();
