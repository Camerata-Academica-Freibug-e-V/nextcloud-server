<?php

declare(strict_types=1);

/**
 * SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

namespace Test\EventDispatcher;

use OC\EventDispatcher\EventDispatcher;
use OC\EventDispatcher\IsolatingEventDispatcher;
use OCP\AppFramework\QueryException;
use OCP\Broadcast\Events\IBroadcastEvent;
use OCP\EventDispatcher\ABroadcastedEvent;
use OCP\EventDispatcher\Event;
use OCP\EventDispatcher\IEventDispatcher;
use OCP\EventDispatcher\IEventListener;
use OCP\Exceptions\AbortedEventException;
use OCP\HintException;
use OCP\Interaction\InteractionRestrictedException;
use OCP\Interaction\RestrictInteractionEvent;
use OCP\Security\Events\ValidatePasswordPolicyEvent;
use OCP\Server;
use PHPUnit\Framework\Attributes\DataProvider;
use Psr\Container\ContainerInterface;
use Psr\Log\LoggerInterface;
use RuntimeException;
use Test\TestCase;
use Throwable;
use TypeError;

class TestBroadcastEvent extends ABroadcastedEvent {
	public function getUids(): array {
		return [];
	}

	public function jsonSerialize(): array {
		return [];
	}
}

class TestNotificationEvent extends Event {
}

class IsolatingEventDispatcherTest extends TestCase {
	private function createDispatcher(ContainerInterface $container, LoggerInterface $logger): EventDispatcher {
		return new EventDispatcher(new IsolatingEventDispatcher($logger), $container, $logger);
	}

	public static function ordinaryFailures(): array {
		return [[new RuntimeException('failure')], [new TypeError('failure')]];
	}

	#[DataProvider('ordinaryFailures')]
	public function testCallableFailureDoesNotInterruptListeners(Throwable $failure): void {
		$logger = $this->createMock(LoggerInterface::class);
		$logger->expects($this->exactly(2))->method('error');
		$dispatcher = $this->createDispatcher($this->createMock(ContainerInterface::class), $logger);
		$calls = [];
		$throwing = static function () use (&$calls, $failure): void {
			$calls[] = 'first';
			throw $failure;
		};
		$removed = static function () use (&$calls): void {
			$calls[] = 'removed';
		};
		$dispatcher->addListener(Event::class, static function () use (&$calls): void {
			$calls[] = 'last';
		}, -1);
		$dispatcher->addListener(Event::class, $throwing, 1);
		$dispatcher->addListener(Event::class, $removed);
		$dispatcher->removeListener(Event::class, $removed);
		$dispatcher->dispatchTyped(new Event());
		$dispatcher->dispatchTyped(new Event());
		$this->assertSame(['first', 'last', 'first', 'last'], $calls);
	}

	public static function serviceFailures(): array {
		return [[new RuntimeException('construction')], [new TypeError('construction')], [new QueryException('construction')]];
	}

	#[DataProvider('serviceFailures')]
	public function testServiceConstructionFailureIsIsolated(Throwable $failure): void {
		$container = $this->createMock(ContainerInterface::class);
		$container->method('get')->willThrowException($failure);
		$logger = $this->createMock(LoggerInterface::class);
		$logger->expects($this->once())->method('error');
		$dispatcher = $this->createDispatcher($container, $logger);
		$ran = false;
		$dispatcher->addServiceListener(Event::class, 'missing');
		$dispatcher->addListener(Event::class, static function () use (&$ran): void {
			$ran = true;
		});
		$dispatcher->dispatchTyped(new Event());
		$this->assertTrue($ran);
	}

	public function testServiceHandleFailureIsIsolated(): void {
		$service = $this->createMock(IEventListener::class);
		$service->method('handle')->willThrowException(new RuntimeException('failure'));
		$container = $this->createMock(ContainerInterface::class);
		$container->method('get')->willReturn($service);
		$logger = $this->createMock(LoggerInterface::class);
		$logger->expects($this->once())->method('error');
		$dispatcher = $this->createDispatcher($container, $logger);
		$ran = false;
		$dispatcher->addServiceListener(Event::class, 'listener');
		$dispatcher->addListener(Event::class, static function () use (&$ran): void {
			$ran = true;
		});
		$dispatcher->dispatchTyped(new Event());
		$this->assertTrue($ran);
	}

	public function testStoppedPropagationPreventsListenersAndBroadcastAfterFailure(): void {
		$logger = $this->createMock(LoggerInterface::class);
		$logger->expects($this->once())->method('error');
		$dispatcher = $this->createDispatcher($this->createMock(ContainerInterface::class), $logger);
		$ran = false;
		$dispatcher->addListener(TestBroadcastEvent::class, static function (Event $event): void {
			$event->stopPropagation();
			throw new RuntimeException('failure');
		});
		$dispatcher->addListener(TestBroadcastEvent::class, static function () use (&$ran): void {
			$ran = true;
		});
		$dispatcher->addListener(IBroadcastEvent::class, static function () use (&$ran): void {
			$ran = true;
		});
		$dispatcher->dispatchTyped(new TestBroadcastEvent());
		$this->assertFalse($ran);
	}

	public function testBroadcastFollowsIsolatedFailure(): void {
		$logger = $this->createMock(LoggerInterface::class);
		$logger->expects($this->once())->method('error');
		$dispatcher = $this->createDispatcher($this->createMock(ContainerInterface::class), $logger);
		$ran = false;
		$dispatcher->addListener(TestBroadcastEvent::class, static function (): void {
			throw new RuntimeException();
		});
		$dispatcher->addListener(IBroadcastEvent::class, static function () use (&$ran): void {
			$ran = true;
		});
		$dispatcher->dispatchTyped(new TestBroadcastEvent());
		$this->assertTrue($ran);
	}

	public static function strictEvents(): array {
		return [
			[new ValidatePasswordPolicyEvent('password'), new RuntimeException('validation')],
			[new ValidatePasswordPolicyEvent('password'), new HintException('invalid', 'hint')],
			[new RestrictInteractionEvent('user', null, [], null, []), new InteractionRestrictedException('denied', 'denied')],
			[new RestrictInteractionEvent('user', null, [], null, []), new TypeError('validation')],
		];
	}

	#[DataProvider('strictEvents')]
	public function testStrictEventPropagatesCallableFailure(Event $event, Throwable $failure): void {
		$logger = $this->createMock(LoggerInterface::class);
		$logger->expects($this->never())->method('error');
		$dispatcher = $this->createDispatcher($this->createMock(ContainerInterface::class), $logger);
		$dispatcher->addListener($event::class, static function () use ($failure): void {
			throw $failure;
		});
		$this->expectException($failure::class);
		$this->expectExceptionMessage($failure->getMessage());
		$dispatcher->dispatchTyped($event);
	}

	#[DataProvider('serviceFailures')]
	public function testStrictEventPropagatesServiceConstructionFailure(Throwable $failure): void {
		$container = $this->createMock(ContainerInterface::class);
		$container->method('get')->willThrowException($failure);
		$dispatcher = $this->createDispatcher($container, $this->createMock(LoggerInterface::class));
		$dispatcher->addServiceListener(ValidatePasswordPolicyEvent::class, 'missing');
		$this->expectException($failure::class);
		$this->expectExceptionMessage($failure->getMessage());
		$dispatcher->dispatchTyped(new ValidatePasswordPolicyEvent('password'));
	}

	public function testStrictEventPropagatesServiceHandleFailure(): void {
		$failure = new RuntimeException('validation');
		$service = $this->createMock(IEventListener::class);
		$service->method('handle')->willThrowException($failure);
		$container = $this->createMock(ContainerInterface::class);
		$container->method('get')->willReturn($service);
		$dispatcher = $this->createDispatcher($container, $this->createMock(LoggerInterface::class));
		$dispatcher->addServiceListener(ValidatePasswordPolicyEvent::class, 'listener');
		$this->expectExceptionObject($failure);
		$dispatcher->dispatchTyped(new ValidatePasswordPolicyEvent('password'));
	}

	public function testAbortedEventExceptionPropagatesForOrdinaryEvent(): void {
		$dispatcher = $this->createDispatcher($this->createMock(ContainerInterface::class), $this->createMock(LoggerInterface::class));
		$dispatcher->addListener(Event::class, static function (): void {
			throw new AbortedEventException();
		});
		$this->expectException(AbortedEventException::class);
		$dispatcher->dispatchTyped(new Event());
	}

	public function testAbortedEventExceptionPropagatesFromServiceListener(): void {
		$service = $this->createMock(IEventListener::class);
		$service->method('handle')->willThrowException(new AbortedEventException('abort'));
		$container = $this->createMock(ContainerInterface::class);
		$container->method('get')->willReturn($service);
		$dispatcher = $this->createDispatcher($container, $this->createMock(LoggerInterface::class));
		$dispatcher->addServiceListener(Event::class, 'listener');
		$this->expectException(AbortedEventException::class);
		$dispatcher->dispatchTyped(new Event());
	}

	public function testNestedStrictFailurePropagatesThroughOrdinaryEvent(): void {
		$dispatcher = $this->createDispatcher($this->createMock(ContainerInterface::class), $this->createMock(LoggerInterface::class));
		$failure = new RuntimeException('validation');
		$dispatcher->addListener(ValidatePasswordPolicyEvent::class, static function () use ($failure): void {
			throw $failure;
		});
		$dispatcher->addListener(Event::class, static function () use ($dispatcher): void {
			$dispatcher->dispatchTyped(new ValidatePasswordPolicyEvent('password'));
		});
		$this->expectExceptionObject($failure);
		$dispatcher->dispatchTyped(new Event());
	}

	public function testServerUsesIsolatingSymfonyDispatcher(): void {
		$dispatcher = Server::get(IEventDispatcher::class);
		$this->assertInstanceOf(EventDispatcher::class, $dispatcher);
		$this->assertInstanceOf(IsolatingEventDispatcher::class, $dispatcher->getSymfonyDispatcher());

		$ran = false;
		$throwing = static function (): void {
			throw new RuntimeException('test listener');
		};
		$subsequent = static function () use (&$ran): void {
			$ran = true;
		};
		$dispatcher->addListener(TestNotificationEvent::class, $throwing);
		$dispatcher->addListener(TestNotificationEvent::class, $subsequent);
		try {
			$dispatcher->getSymfonyDispatcher()->dispatch(new TestNotificationEvent());
			$this->assertTrue($ran);
		} finally {
			$dispatcher->removeListener(TestNotificationEvent::class, $throwing);
			$dispatcher->removeListener(TestNotificationEvent::class, $subsequent);
		}
	}
}
