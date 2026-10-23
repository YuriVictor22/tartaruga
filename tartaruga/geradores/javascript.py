"""
Gerador de JavaScript: monta treze padrões avançados a partir de parâmetros.

Mesmo espírito dos geradores de HTML e CSS — funções puras, sem rede nem
arquivo, fáceis de testar isoladamente. Cobre os tópicos "avançados" de
JavaScript mais pedidos na prática (closures, higher-order functions,
currying, Promises, async/await, classes com campo privado, generators,
Proxy) como TEMPLATES prontos, não como geração livre pelo LLM — o mesmo
raciocínio já aplicado a HTML e CSS: um padrão nomeado e bem definido não
precisa de um modelo de linguagem para ser montado, e um template testado é
mais previsível que uma geração probabilística. O reforço por LLM continua
existindo para o que não é um destes padrões fixos.
"""


def debounce() -> str:
    """Debounce: atrasa a execução até o disparo parar por um tempo."""
    return """function debounce(fn, espera = 300) {
  let temporizador;
  return function (...args) {
    clearTimeout(temporizador);
    temporizador = setTimeout(() => fn.apply(this, args), espera);
  };
}

// Exemplo de uso:
// const aoDigitar = debounce(() => console.log('buscando...'), 300);
// campoDeBusca.addEventListener('input', aoDigitar);"""


def throttle() -> str:
    """Throttle: limita a execução a no máximo uma vez por intervalo."""
    return """function throttle(fn, intervalo = 300) {
  let bloqueado = false;
  return function (...args) {
    if (bloqueado) return;
    fn.apply(this, args);
    bloqueado = true;
    setTimeout(() => { bloqueado = false; }, intervalo);
  };
}

// Exemplo de uso:
// const aoRolar = throttle(() => console.log('rolando...'), 200);
// window.addEventListener('scroll', aoRolar);"""


def memoize() -> str:
    """Cache de resultados por combinação de argumentos (memoization)."""
    return """function memoize(fn) {
  const cache = new Map();
  return function (...args) {
    const chave = JSON.stringify(args);
    if (cache.has(chave)) return cache.get(chave);
    const resultado = fn.apply(this, args);
    cache.set(chave, resultado);
    return resultado;
  };
}

// Exemplo de uso:
// const fibonacciRapido = memoize(function fib(n) {
//   return n <= 1 ? n : fib(n - 1) + fib(n - 2);
// });"""


def curry() -> str:
    """Currying: transforma f(a, b, c) em f(a)(b)(c), aplicando aos poucos."""
    return """function curry(fn) {
  return function curried(...args) {
    if (args.length >= fn.length) return fn.apply(this, args);
    return (...proximos) => curried.apply(this, [...args, ...proximos]);
  };
}

// Exemplo de uso:
// const somarTres = curry((a, b, c) => a + b + c);
// somarTres(1)(2)(3); // 6
// somarTres(1, 2)(3); // 6"""


def clone_profundo() -> str:
    """Clonagem profunda: copia objetos/arrays sem manter referência ao original."""
    return """function clonarProfundo(valor) {
  if (typeof structuredClone === 'function') {
    return structuredClone(valor);
  }
  // Alternativa para ambientes sem structuredClone (não lida com funções,
  // Map, Set ou referências circulares, mas cobre o caso comum):
  return JSON.parse(JSON.stringify(valor));
}

// Exemplo de uso:
// const original = { nome: 'a', tags: ['x', 'y'] };
// const copia = clonarProfundo(original);
// copia.tags.push('z'); // não afeta original.tags"""


def emissor_eventos() -> str:
    """Emissor de eventos (padrão pub/sub): registra, dispara e remove ouvintes."""
    return """class EmissorEventos {
  constructor() {
    this.ouvintes = new Map();
  }

  on(evento, callback) {
    if (!this.ouvintes.has(evento)) {
      this.ouvintes.set(evento, []);
    }
    this.ouvintes.get(evento).push(callback);
    return this;
  }

  off(evento, callback) {
    const lista = this.ouvintes.get(evento);
    if (!lista) return this;
    this.ouvintes.set(evento, lista.filter((cb) => cb !== callback));
    return this;
  }

  emit(evento, ...dados) {
    const lista = this.ouvintes.get(evento) || [];
    lista.forEach((callback) => callback(...dados));
    return this;
  }
}

// Exemplo de uso:
// const bus = new EmissorEventos();
// bus.on('pedido:criado', (pedido) => console.log('novo pedido', pedido));
// bus.emit('pedido:criado', { id: 1 });"""


def promise_retry() -> str:
    """Repete uma operação assíncrona algumas vezes antes de desistir."""
    return """async function tentarNovamente(operacao, tentativas = 3, esperaMs = 500) {
  for (let tentativa = 1; tentativa <= tentativas; tentativa++) {
    try {
      return await operacao();
    } catch (erro) {
      if (tentativa === tentativas) throw erro;
      await new Promise((resolve) => setTimeout(resolve, esperaMs));
    }
  }
}

// Exemplo de uso:
// const dados = await tentarNovamente(() => fetch('/api/dados').then((r) => r.json()));"""


def promise_timeout() -> str:
    """Rejeita uma Promise se ela demorar demais para resolver (Promise.race)."""
    return """function comLimiteDeTempo(promessa, limiteMs = 5000) {
  const tempoEsgotado = new Promise((_, reject) =>
    setTimeout(() => reject(new Error('Tempo limite excedido')), limiteMs)
  );
  return Promise.race([promessa, tempoEsgotado]);
}

// Exemplo de uso:
// const resultado = await comLimiteDeTempo(fetch('/api/lento'), 3000);"""


def busca_assincrona() -> str:
    """Requisição HTTP com async/await e tratamento de erro/status HTTP."""
    return """async function buscarDados(url) {
  try {
    const resposta = await fetch(url);
    if (!resposta.ok) {
      throw new Error(`Erro HTTP: ${resposta.status}`);
    }
    return await resposta.json();
  } catch (erro) {
    console.error('Falha ao buscar dados:', erro.message);
    throw erro;
  }
}

// Exemplo de uso:
// const usuario = await buscarDados('/api/usuario/1');"""


def classe_com_heranca() -> str:
    """Classes com herança, campo privado (#) e getter — os pilares de POO em JS."""
    return """class Animal {
  #energia = 100;

  constructor(nome) {
    this.nome = nome;
  }

  get energia() {
    return this.#energia;
  }

  mover(gasto = 10) {
    this.#energia = Math.max(0, this.#energia - gasto);
    return `${this.nome} se moveu. Energia: ${this.#energia}`;
  }
}

class Passaro extends Animal {
  voar() {
    return `${this.nome} está voando. ${this.mover(20)}`;
  }
}

// Exemplo de uso:
// const ave = new Passaro('Coruja');
// console.log(ave.voar());"""


def gerador_sequencia() -> str:
    """Function generator: produz valores sob demanda, sem guardar tudo em memória."""
    return """function* gerarIntervalo(inicio, fim, passo = 1) {
  for (let atual = inicio; atual <= fim; atual += passo) {
    yield atual;
  }
}

// Exemplo de uso:
// for (const numero of gerarIntervalo(1, 10, 2)) {
//   console.log(numero); // 1, 3, 5, 7, 9
// }"""


def singleton() -> str:
    """Singleton com closure: garante uma única instância compartilhada."""
    return """const ConfiguracaoApp = (function () {
  let instancia;

  function criarInstancia() {
    return { tema: 'claro', idioma: 'pt-BR' };
  }

  return {
    obter() {
      if (!instancia) {
        instancia = criarInstancia();
      }
      return instancia;
    },
  };
})();

// Exemplo de uso:
// const config1 = ConfiguracaoApp.obter();
// const config2 = ConfiguracaoApp.obter();
// config1 === config2; // true"""


def validador_proxy() -> str:
    """Proxy: intercepta leitura/escrita de um objeto para validar em tempo real."""
    return """function criarObjetoValidado(alvo, regras) {
  return new Proxy(alvo, {
    set(objeto, propriedade, valor) {
      const valido = regras[propriedade];
      if (valido && !valido(valor)) {
        throw new TypeError(`Valor inválido para "${String(propriedade)}"`);
      }
      objeto[propriedade] = valor;
      return true;
    },
  });
}

// Exemplo de uso:
// const usuario = criarObjetoValidado(
//   { idade: 0 },
//   { idade: (valor) => typeof valor === 'number' && valor >= 0 }
// );
// usuario.idade = 25;   // ok
// usuario.idade = -1;   // lança TypeError"""
