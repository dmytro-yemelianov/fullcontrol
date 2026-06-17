//! The core sequential state-walk - the microkernel proper.
//!
//! A design flattened by the Python wrapper (`fullcontrol/ir/kernel.py`) into primitive columns is
//! walked once here, producing the resolved per-move columns (struct-of-arrays). This is a pure
//! arithmetic fold: Rust never touches a Python object. Both `resolve_columnar` (returns the
//! columns) and `simulate` (folds them into metrics) run this single walk.
//!
//! Step tags (must match kernel.py):
//!   0 Point:               a=x  b=y  c=z              (NaN component => inherit previous)
//!   1 Extruder:            a=on (-1 none / 0 off / 1 on)  b=volume_to_e (NaN => no change)
//!   2 ExtrusionGeometry:   a=area (NaN => None/0)  b=width  c=height
//!   3 Printer:             a=print_speed (NaN => no change)  b=travel_speed (NaN => no change)
//!   4 StationaryExtrusion: a=volume
//!   5 Arc:                 a=end_x b=end_y c=end_z (absolute, already resolved)  d=arc_length
//!  -1 no-op (e.g. ManualGcode injected by the primer) - keeps source_index aligned.

pub const TAG_POINT: i64 = 0;
pub const TAG_EXTRUDER: i64 = 1;
pub const TAG_GEOMETRY: i64 = 2;
pub const TAG_PRINTER: i64 = 3;
pub const TAG_STATIONARY: i64 = 4;
pub const TAG_ARC: i64 = 5;

/// The flattened design: parallel primitive columns (one row per resolved step).
pub struct Steps {
    pub tag: Vec<i64>,
    pub a: Vec<f64>,
    pub b: Vec<f64>,
    pub c: Vec<f64>,
    pub d: Vec<f64>,
}

/// The running context, seeded from the gcode State and mutated through the walk.
pub struct Ctx {
    pub on: f64, // -1 none / 0 off / 1 on
    pub volume_to_e: f64,
    pub print_speed: f64,
    pub travel_speed: f64,
    pub area: f64, // NaN => None
    pub width: f64,
    pub height: f64,
    pub px: f64,
    pub py: f64,
    pub pz: f64,
}

impl Ctx {
    /// Seed from the ten initial-context scalars (order matches kernel.py `_init_args`).
    pub fn from_scalars(s: &[f64]) -> Ctx {
        Ctx {
            on: s[0],
            volume_to_e: s[1],
            print_speed: s[2],
            travel_speed: s[3],
            area: s[4],
            width: s[5],
            height: s[6],
            px: s[7],
            py: s[8],
            pz: s[9],
        }
    }

    #[inline]
    fn extruding(&self) -> bool {
        self.on > 0.5
    }
}

/// Resolved per-move columns plus the stationary-material scalars. Mirrors ColumnarToolpath.
pub struct ResolveOut {
    pub sx: Vec<f64>,
    pub sy: Vec<f64>,
    pub sz: Vec<f64>,
    pub ex: Vec<f64>,
    pub ey: Vec<f64>,
    pub ez: Vec<f64>,
    pub travel: Vec<bool>,
    pub speed: Vec<f64>,
    pub length: Vec<f64>,
    pub vol: Vec<f64>,
    pub fil: Vec<f64>,
    pub src: Vec<i64>,
    pub wid: Vec<f64>,
    pub hgt: Vec<f64>,
    pub material_volume: f64,
    pub material_filament: f64,
}

impl ResolveOut {
    fn with_capacity(n: usize) -> ResolveOut {
        ResolveOut {
            sx: Vec::with_capacity(n),
            sy: Vec::with_capacity(n),
            sz: Vec::with_capacity(n),
            ex: Vec::with_capacity(n),
            ey: Vec::with_capacity(n),
            ez: Vec::with_capacity(n),
            travel: Vec::with_capacity(n),
            speed: Vec::with_capacity(n),
            length: Vec::with_capacity(n),
            vol: Vec::with_capacity(n),
            fil: Vec::with_capacity(n),
            src: Vec::with_capacity(n),
            wid: Vec::with_capacity(n),
            hgt: Vec::with_capacity(n),
            material_volume: 0.0,
            material_filament: 0.0,
        }
    }

    /// Emit one resolved move row from the current running context (shared by Point and Arc).
    fn push_move(&mut self, ctx: &Ctx, start: [f64; 3], end: [f64; 3], ln: f64, i: usize) {
        let extruding = ctx.extruding();
        let spd = if extruding {
            ctx.print_speed
        } else {
            ctx.travel_speed
        };
        let v = if extruding { ln * or_0(ctx.area) } else { 0.0 };
        self.sx.push(start[0]);
        self.sy.push(start[1]);
        self.sz.push(start[2]);
        self.ex.push(end[0]);
        self.ey.push(end[1]);
        self.ez.push(end[2]);
        self.travel.push(!extruding);
        self.speed.push(spd);
        self.length.push(ln);
        self.vol.push(v);
        self.fil.push(v * or_0(ctx.volume_to_e));
        self.src.push(i as i64);
        self.wid.push(ctx.width);
        self.hgt.push(ctx.height);
    }
}

/// NaN-aware "same coordinate" (treats NaN==NaN, i.e. both still undefined).
#[inline]
fn same(p: f64, q: f64) -> bool {
    (p.is_nan() && q.is_nan()) || p == q
}

#[inline]
fn or_0(v: f64) -> f64 {
    if v.is_nan() {
        0.0
    } else {
        v
    }
}

/// Run the walk, emitting one row per move (a Point that changes position, or an Arc).
pub fn walk(steps: &Steps, ctx: &mut Ctx) -> ResolveOut {
    let n = steps.tag.len();
    let (a, b, c, d) = (&steps.a, &steps.b, &steps.c, &steps.d);
    let mut out = ResolveOut::with_capacity(n);

    for i in 0..n {
        match steps.tag[i] {
            TAG_POINT => {
                let start = [ctx.px, ctx.py, ctx.pz];
                let (sxv, syv, szv) = (a[i], b[i], c[i]);
                let dx = if start[0].is_nan() || sxv.is_nan() {
                    0.0
                } else {
                    sxv - start[0]
                };
                let dy = if start[1].is_nan() || syv.is_nan() {
                    0.0
                } else {
                    syv - start[1]
                };
                let dz = if start[2].is_nan() || szv.is_nan() {
                    0.0
                } else {
                    szv - start[2]
                };
                if !sxv.is_nan() {
                    ctx.px = sxv;
                }
                if !syv.is_nan() {
                    ctx.py = syv;
                }
                if !szv.is_nan() {
                    ctx.pz = szv;
                }
                let end = [ctx.px, ctx.py, ctx.pz];
                if !same(start[0], end[0]) || !same(start[1], end[1]) || !same(start[2], end[2]) {
                    let ln = (dx * dx + dy * dy + dz * dz).sqrt();
                    out.push_move(ctx, start, end, ln, i);
                }
            }
            TAG_ARC => {
                // end is already resolved (absolute) in Python; d carries the arc length.
                let start = [ctx.px, ctx.py, ctx.pz];
                ctx.px = a[i];
                ctx.py = b[i];
                ctx.pz = c[i];
                let end = [ctx.px, ctx.py, ctx.pz];
                out.push_move(ctx, start, end, d[i], i);
            }
            TAG_STATIONARY => {
                let volume = a[i];
                out.material_volume += volume;
                out.material_filament += volume * or_0(ctx.volume_to_e);
            }
            TAG_EXTRUDER => {
                if a[i] >= -0.5 {
                    ctx.on = a[i]; // -1 (None) => no change
                }
                if !b[i].is_nan() {
                    ctx.volume_to_e = b[i];
                }
            }
            TAG_GEOMETRY => {
                ctx.area = a[i];
                ctx.width = b[i];
                ctx.height = c[i];
            }
            TAG_PRINTER => {
                if !a[i].is_nan() {
                    ctx.print_speed = a[i];
                }
                if !b[i].is_nan() {
                    ctx.travel_speed = b[i];
                }
            }
            _ => {}
        }
    }

    out
}
