// orientation3d.js — modelo 3D do CanSat em WebGL puro (sem three.js).
//
// Conteúdo idêntico ao do dashboard original (OrientationRenderer + funções de
// matriz), apenas movido para um módulo. A instanciação e o load() do modelo
// agora são feitos em main.js.
//
// Uso:
//   const renderer = new OrientationRenderer(canvas);
//   await renderer.load("model.obj");
//   renderer.setRotation(roll, pitch, yaw);   // graus

export class OrientationRenderer {

    constructor(canvas) {
        this.canvas =
            canvas;

        this.gl =
            canvas?.getContext(
                "webgl",
                {
                    alpha: true,
                    antialias: true,
                    premultipliedAlpha: true
                }
            ) || null;

        this.loaded =
            false;

        this.vertexCount =
            0;

        this.positionBuffer =
            null;

        this.normalBuffer =
            null;

        this.center =
            [0, 0, 0];

        this.size =
            1;

        this.rotation = {
            x: 0,
            y: 0,
            z: 0
        };

        if (!this.gl) {
            console.warn(
                "WebGL não disponível; modelo 3D desativado."
            );

            return;
        }

        this.initProgram();

        this.gl.enable(
            this.gl.DEPTH_TEST
        );

        this.gl.depthFunc(
            this.gl.LEQUAL
        );

        this.render =
            this.render.bind(this);

        requestAnimationFrame(
            this.render
        );
    }

    createShader(type, source) {
        const gl =
            this.gl;

        const shader =
            gl.createShader(type);

        gl.shaderSource(
            shader,
            source
        );

        gl.compileShader(
            shader
        );

        if (
            !gl.getShaderParameter(
                shader,
                gl.COMPILE_STATUS
            )
        ) {
            const message =
                gl.getShaderInfoLog(
                    shader
                );

            gl.deleteShader(
                shader
            );

            throw new Error(
                message
            );
        }

        return shader;
    }

    initProgram() {
        const gl =
            this.gl;

        const vertexSource = `
            attribute vec3 aPosition;
            attribute vec3 aNormal;

            uniform mat4 uProjection;
            uniform mat4 uModel;

            varying vec3 vNormal;
            varying vec3 vPosition;

            void main() {
                vec4 worldPosition =
                    uModel *
                    vec4(aPosition, 1.0);

                gl_Position =
                    uProjection *
                    worldPosition;

                vPosition =
                    worldPosition.xyz;

                vNormal =
                    normalize(
                        mat3(uModel) *
                        aNormal
                    );
            }
        `;

        const fragmentSource = `
            precision mediump float;

            varying vec3 vNormal;
            varying vec3 vPosition;

            void main() {
                vec3 normal =
                    normalize(vNormal);

                vec3 lightA =
                    normalize(
                        vec3(
                            0.55,
                            0.80,
                            1.00
                        )
                    );

                vec3 lightB =
                    normalize(
                        vec3(
                            -0.80,
                            0.20,
                            0.40
                        )
                    );

                float diffuseA =
                    max(
                        dot(
                            normal,
                            lightA
                        ),
                        0.0
                    );

                float diffuseB =
                    max(
                        dot(
                            normal,
                            lightB
                        ),
                        0.0
                    ) * 0.28;

                float rim =
                    pow(
                        1.0 -
                        abs(normal.z),
                        2.0
                    ) * 0.24;

                float light =
                    0.28 +
                    diffuseA * 0.64 +
                    diffuseB +
                    rim;

                vec3 base =
                    vec3(
                        0.93,
                        0.63,
                        0.18
                    );

                vec3 highlight =
                    vec3(
                        1.0,
                        0.84,
                        0.52
                    );

                vec3 color =
                    mix(
                        base,
                        highlight,
                        diffuseA * 0.30
                    ) * light;

                gl_FragColor =
                    vec4(
                        color,
                        1.0
                    );
            }
        `;

        const vertexShader =
            this.createShader(
                gl.VERTEX_SHADER,
                vertexSource
            );

        const fragmentShader =
            this.createShader(
                gl.FRAGMENT_SHADER,
                fragmentSource
            );

        this.program =
            gl.createProgram();

        gl.attachShader(
            this.program,
            vertexShader
        );

        gl.attachShader(
            this.program,
            fragmentShader
        );

        gl.linkProgram(
            this.program
        );

        if (
            !gl.getProgramParameter(
                this.program,
                gl.LINK_STATUS
            )
        ) {
            throw new Error(
                gl.getProgramInfoLog(
                    this.program
                )
            );
        }

        this.locations = {
            position:
                gl.getAttribLocation(
                    this.program,
                    "aPosition"
                ),

            normal:
                gl.getAttribLocation(
                    this.program,
                    "aNormal"
                ),

            projection:
                gl.getUniformLocation(
                    this.program,
                    "uProjection"
                ),

            model:
                gl.getUniformLocation(
                    this.program,
                    "uModel"
                )
        };
    }

    async load(path) {
        if (!this.gl) {
            return;
        }

        try {
            const response =
                await fetch(
                    path,
                    {
                        cache: "no-store"
                    }
                );

            if (!response.ok) {
                throw new Error(
                    `HTTP ${response.status}`
                );
            }

            const mesh =
                this.parseObj(
                    await response.text()
                );

            this.upload(mesh);

            this.loaded =
                true;

        } catch (error) {
            console.error(
                "Erro ao carregar model.obj:",
                error
            );
        }
    }

    parseObj(text) {
        const positions = [];
        const triangles = [];
        const normals = [];

        for (
            const rawLine of
            text.split(/\r?\n/)
        ) {
            const line =
                rawLine.trim();

            if (
                !line ||
                line.startsWith("#")
            ) {
                continue;
            }

            const parts =
                line.split(/\s+/);

            if (
                parts[0] === "v" &&
                parts.length >= 4
            ) {
                positions.push([
                    Number(parts[1]),
                    Number(parts[2]),
                    Number(parts[3])
                ]);

                continue;
            }

            if (
                parts[0] !== "f" ||
                parts.length < 4
            ) {
                continue;
            }

            const face =
                parts
                    .slice(1)
                    .map(
                        (token) => {
                            const rawIndex =
                                Number(
                                    token
                                        .split("/")[0]
                                );

                            return rawIndex > 0
                                ? rawIndex - 1
                                : positions.length +
                                  rawIndex;
                        }
                    );

            for (
                let i = 1;
                i < face.length - 1;
                i++
            ) {
                const a =
                    positions[
                        face[0]
                    ];

                const b =
                    positions[
                        face[i]
                    ];

                const c =
                    positions[
                        face[i + 1]
                    ];

                if (!a || !b || !c) {
                    continue;
                }

                const normal =
                    triangleNormal(
                        a,
                        b,
                        c
                    );

                triangles.push(
                    ...a,
                    ...b,
                    ...c
                );

                normals.push(
                    ...normal,
                    ...normal,
                    ...normal
                );
            }
        }

        if (
            !positions.length ||
            !triangles.length
        ) {
            throw new Error(
                "OBJ sem geometria utilizável."
            );
        }

        const bounds =
            getBounds(positions);

        return {
            triangles,
            normals,
            ...bounds
        };
    }

    upload(mesh) {
        const gl =
            this.gl;

        this.center =
            mesh.center;

        this.size =
            mesh.size;

        this.vertexCount =
            mesh.triangles.length /
            3;

        this.positionBuffer =
            gl.createBuffer();

        gl.bindBuffer(
            gl.ARRAY_BUFFER,
            this.positionBuffer
        );

        gl.bufferData(
            gl.ARRAY_BUFFER,
            new Float32Array(
                mesh.triangles
            ),
            gl.STATIC_DRAW
        );

        this.normalBuffer =
            gl.createBuffer();

        gl.bindBuffer(
            gl.ARRAY_BUFFER,
            this.normalBuffer
        );

        gl.bufferData(
            gl.ARRAY_BUFFER,
            new Float32Array(
                mesh.normals
            ),
            gl.STATIC_DRAW
        );
    }

    setRotation(
        roll,
        pitch,
        yaw
    ) {
        this.rotation.x =
            roll;

        this.rotation.y =
            pitch;

        this.rotation.z =
            yaw;
    }

    resize() {
        const gl =
            this.gl;

        const rect =
            this.canvas
                .getBoundingClientRect();

        const dpr =
            Math.min(
                window.devicePixelRatio || 1,
                2
            );

        const width =
            Math.max(
                1,
                Math.round(
                    rect.width * dpr
                )
            );

        const height =
            Math.max(
                1,
                Math.round(
                    rect.height * dpr
                )
            );

        if (
            this.canvas.width !== width ||
            this.canvas.height !== height
        ) {
            this.canvas.width =
                width;

            this.canvas.height =
                height;
        }

        gl.viewport(
            0,
            0,
            width,
            height
        );

        return width / height;
    }

    render() {
        const gl =
            this.gl;

        if (!gl) {
            return;
        }

        const aspect =
            this.resize();

        gl.clearColor(
            0,
            0,
            0,
            0
        );

        gl.clear(
            gl.COLOR_BUFFER_BIT |
            gl.DEPTH_BUFFER_BIT
        );

        if (this.loaded) {
            const projection =
                perspective(
                    34,
                    aspect,
                    0.1,
                    100
                );

            const scale =
                2.6 /
                Math.max(
                    this.size,
                    0.001
                );

            let model =
                identity();

            model =
                multiply(
                    model,
                    translation(
                        -this.center[0],
                        -this.center[1],
                        -this.center[2]
                    )
                );

            model =
                multiply(
                    model,
                    scaleMatrix(
                        scale
                    )
                );

            /*
             * Pequeno ângulo fixo de apresentação.
             * Serve apenas para visualizar melhor o objeto.
             */
            model =
                multiply(
                    rotationY(18),
                    model
                );

            model =
                multiply(
                    rotationX(-8),
                    model
                );

            /*
             * Atitude dinâmica do CanSat.
             */
            model =
                multiply(
                    rotationZ(
                        this.rotation.z
                    ),
                    model
                );

            model =
                multiply(
                    rotationY(
                        this.rotation.y
                    ),
                    model
                );

            model =
                multiply(
                    rotationX(
                        this.rotation.x
                    ),
                    model
                );

            model =
                multiply(
                    translation(
                        0,
                        0,
                        -6.2
                    ),
                    model
                );

            gl.useProgram(
                this.program
            );

            gl.uniformMatrix4fv(
                this.locations.projection,
                false,
                new Float32Array(
                    projection
                )
            );

            gl.uniformMatrix4fv(
                this.locations.model,
                false,
                new Float32Array(
                    model
                )
            );

            gl.bindBuffer(
                gl.ARRAY_BUFFER,
                this.positionBuffer
            );

            gl.enableVertexAttribArray(
                this.locations.position
            );

            gl.vertexAttribPointer(
                this.locations.position,
                3,
                gl.FLOAT,
                false,
                0,
                0
            );

            gl.bindBuffer(
                gl.ARRAY_BUFFER,
                this.normalBuffer
            );

            gl.enableVertexAttribArray(
                this.locations.normal
            );

            gl.vertexAttribPointer(
                this.locations.normal,
                3,
                gl.FLOAT,
                false,
                0,
                0
            );

            gl.drawArrays(
                gl.TRIANGLES,
                0,
                this.vertexCount
            );
        }

        requestAnimationFrame(
            this.render
        );
    }
}

function triangleNormal(
    a,
    b,
    c
) {
    const ux =
        b[0] - a[0];

    const uy =
        b[1] - a[1];

    const uz =
        b[2] - a[2];

    const vx =
        c[0] - a[0];

    const vy =
        c[1] - a[1];

    const vz =
        c[2] - a[2];

    let nx =
        uy * vz -
        uz * vy;

    let ny =
        uz * vx -
        ux * vz;

    let nz =
        ux * vy -
        uy * vx;

    const length =
        Math.hypot(
            nx,
            ny,
            nz
        ) || 1;

    nx /= length;
    ny /= length;
    nz /= length;

    return [
        nx,
        ny,
        nz
    ];
}

function getBounds(positions) {
    const min = [
        Infinity,
        Infinity,
        Infinity
    ];

    const max = [
        -Infinity,
        -Infinity,
        -Infinity
    ];

    for (
        const position of
        positions
    ) {
        for (
            let axis = 0;
            axis < 3;
            axis++
        ) {
            min[axis] =
                Math.min(
                    min[axis],
                    position[axis]
                );

            max[axis] =
                Math.max(
                    max[axis],
                    position[axis]
                );
        }
    }

    const center = [
        (min[0] + max[0]) / 2,
        (min[1] + max[1]) / 2,
        (min[2] + max[2]) / 2
    ];

    const size =
        Math.max(
            max[0] - min[0],
            max[1] - min[1],
            max[2] - min[2]
        );

    return {
        center,
        size
    };
}

function identity() {
    return [
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1
    ];
}

function multiply(a, b) {
    const result =
        new Array(16);

    for (
        let column = 0;
        column < 4;
        column++
    ) {
        for (
            let row = 0;
            row < 4;
            row++
        ) {
            result[
                column * 4 + row
            ] =
                a[row] *
                    b[column * 4] +

                a[4 + row] *
                    b[column * 4 + 1] +

                a[8 + row] *
                    b[column * 4 + 2] +

                a[12 + row] *
                    b[column * 4 + 3];
        }
    }

    return result;
}

function rotationX(degrees) {
    const angle =
        degrees *
        Math.PI /
        180;

    const c =
        Math.cos(angle);

    const s =
        Math.sin(angle);

    return [
        1, 0, 0, 0,
        0, c, s, 0,
        0, -s, c, 0,
        0, 0, 0, 1
    ];
}

function rotationY(degrees) {
    const angle =
        degrees *
        Math.PI /
        180;

    const c =
        Math.cos(angle);

    const s =
        Math.sin(angle);

    return [
        c, 0, -s, 0,
        0, 1, 0, 0,
        s, 0, c, 0,
        0, 0, 0, 1
    ];
}

function rotationZ(degrees) {
    const angle =
        degrees *
        Math.PI /
        180;

    const c =
        Math.cos(angle);

    const s =
        Math.sin(angle);

    return [
        c, s, 0, 0,
        -s, c, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1
    ];
}

function translation(
    x,
    y,
    z
) {
    return [
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        x, y, z, 1
    ];
}

function scaleMatrix(value) {
    return [
        value, 0, 0, 0,
        0, value, 0, 0,
        0, 0, value, 0,
        0, 0, 0, 1
    ];
}

function perspective(
    fovDegrees,
    aspect,
    near,
    far
) {
    const f =
        1 /
        Math.tan(
            (
                fovDegrees *
                Math.PI /
                180
            ) / 2
        );

    const nf =
        1 /
        (near - far);

    return [
        f / aspect, 0, 0, 0,
        0, f, 0, 0,
        0, 0,
        (far + near) * nf,
        -1,
        0, 0,
        2 * far * near * nf,
        0
    ];
}

